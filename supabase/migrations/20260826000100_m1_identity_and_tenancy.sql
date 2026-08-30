-- M1 identity and tenancy baseline.
--
-- Recovery: this migration is additive. Before production data exists, recovery may drop the
-- app/app_private schemas and the api_login/app_api roles. After production data exists, prefer a
-- forward migration; dropping these objects deletes organization and membership data.

do $$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'app_api') then
    create role app_api
      nologin
      noinherit
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls;
  end if;

  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'api_login') then
    create role api_login
      login
      noinherit
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls;
  end if;
end
$$;

-- Supabase applies migrations with a role that may create ordinary roles but may not alter
-- superuser-only attributes. The guarded CREATE ROLE statements above establish the complete
-- least-privilege attributes; repeated local resets preserve those cluster-level roles.
alter role app_api noinherit;
alter role api_login noinherit;
grant app_api to api_login;
-- The database owner needs to assume the restricted role for migration verification and policy
-- tests. This does not add privileges to the already administrative owner.
grant app_api to postgres;

create schema if not exists app;
create schema if not exists app_private;

revoke all on schema app from public, anon, authenticated, service_role;
revoke all on schema app_private from public, anon, authenticated, service_role;
grant usage on schema app to app_api;
grant usage on schema app_private to app_api;

alter default privileges in schema app revoke all on tables from public, anon, authenticated, service_role;
alter default privileges in schema app revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges in schema app revoke execute on functions from public, anon, authenticated, service_role;
alter default privileges in schema app_private revoke execute on functions from public, anon, authenticated, service_role;

create table app.user_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_profiles_display_name_valid check (
    display_name is null
    or (
      display_name = btrim(display_name)
      and char_length(display_name) between 1 and 100
    )
  )
);

create table app.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_by_user_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organizations_name_valid check (
    name = btrim(name)
    and char_length(name) between 1 and 100
  )
);

create table app.organization_memberships (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references app.organizations (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organization_memberships_role_valid check (role in ('owner', 'admin', 'member')),
  constraint organization_memberships_organization_user_unique unique (organization_id, user_id)
);

create index organization_memberships_user_id_idx
  on app.organization_memberships (user_id);
create index organization_memberships_organization_role_idx
  on app.organization_memberships (organization_id, role);

create function app_private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger user_profiles_set_updated_at
before update on app.user_profiles
for each row execute function app_private.set_updated_at();

create trigger organizations_set_updated_at
before update on app.organizations
for each row execute function app_private.set_updated_at();

create trigger organization_memberships_set_updated_at
before update on app.organization_memberships
for each row execute function app_private.set_updated_at();

create function app_private.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  candidate_display_name text;
begin
  candidate_display_name := nullif(btrim(new.raw_user_meta_data ->> 'display_name'), '');

  if char_length(candidate_display_name) > 100 then
    candidate_display_name := null;
  end if;

  insert into app.user_profiles (user_id, display_name)
  values (new.id, candidate_display_name)
  on conflict (user_id) do nothing;

  return new;
end;
$$;

insert into app.user_profiles (user_id)
select id
from auth.users
on conflict (user_id) do nothing;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function app_private.handle_new_auth_user();

create function app_private.current_membership_role(target_organization_id uuid)
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select membership.role
  from app.organization_memberships as membership
  where membership.organization_id = target_organization_id
    and membership.user_id = (select auth.uid())
  limit 1
$$;

create function app_private.shares_organization_with(target_user_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from app.organization_memberships as actor_membership
    inner join app.organization_memberships as target_membership
      on target_membership.organization_id = actor_membership.organization_id
    where actor_membership.user_id = (select auth.uid())
      and target_membership.user_id = target_user_id
  )
$$;

create function app_private.can_bootstrap_organization_owner(
  target_organization_id uuid,
  target_user_id uuid,
  target_role text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select target_role = 'owner'
    and target_user_id = (select auth.uid())
    and exists (
      select 1
      from app.organizations as organization
      where organization.id = target_organization_id
        and organization.created_by_user_id = (select auth.uid())
    )
    and not exists (
      select 1
      from app.organization_memberships as membership
      where membership.organization_id = target_organization_id
    )
$$;

create function app_private.prevent_last_owner_removal()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  removes_owner boolean;
begin
  if old.role <> 'owner' then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if tg_op = 'DELETE' then
    removes_owner := true;
  else
    removes_owner := new.role <> 'owner';
  end if;

  if not removes_owner then
    return new;
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(old.organization_id::text, 0)
  );

  if not exists (
    select 1
    from app.organization_memberships as membership
    where membership.organization_id = old.organization_id
      and membership.id <> old.id
      and membership.role = 'owner'
  ) then
    raise exception using
      errcode = '23514',
      message = 'organization must retain at least one owner';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create trigger organization_memberships_retain_owner
before update of role or delete on app.organization_memberships
for each row execute function app_private.prevent_last_owner_removal();

revoke execute on all functions in schema app_private from public, anon, authenticated, service_role;
grant execute on function app_private.current_membership_role(uuid) to app_api;
grant execute on function app_private.shares_organization_with(uuid) to app_api;
grant execute on function app_private.can_bootstrap_organization_owner(uuid, uuid, text) to app_api;

revoke all on all tables in schema app from public, anon, authenticated, service_role;
grant select on app.user_profiles to app_api;
grant update (display_name) on app.user_profiles to app_api;
grant select, insert on app.organizations to app_api;
grant update (name) on app.organizations to app_api;
grant select, insert, delete on app.organization_memberships to app_api;
grant update (role) on app.organization_memberships to app_api;

alter table app.user_profiles enable row level security;
alter table app.user_profiles force row level security;
alter table app.organizations enable row level security;
alter table app.organizations force row level security;
alter table app.organization_memberships enable row level security;
alter table app.organization_memberships force row level security;

create policy user_profiles_select
on app.user_profiles
for select
to app_api
using (
  (select auth.uid()) is not null
  and (
    user_id = (select auth.uid())
    or (select app_private.shares_organization_with(user_id))
  )
);

create policy user_profiles_update
on app.user_profiles
for update
to app_api
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

create policy organizations_select
on app.organizations
for select
to app_api
using ((select app_private.current_membership_role(id)) is not null);

create policy organizations_insert
on app.organizations
for insert
to app_api
with check (
  (select auth.uid()) is not null
  and created_by_user_id = (select auth.uid())
);

create policy organizations_update
on app.organizations
for update
to app_api
using ((select app_private.current_membership_role(id)) in ('owner', 'admin'))
with check ((select app_private.current_membership_role(id)) in ('owner', 'admin'));

create policy organization_memberships_select
on app.organization_memberships
for select
to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);

create policy organization_memberships_insert
on app.organization_memberships
for insert
to app_api
with check (
  (select auth.uid()) is not null
  and (
    (select app_private.can_bootstrap_organization_owner(organization_id, user_id, role))
    or (select app_private.current_membership_role(organization_id)) = 'owner'
    or (
      (select app_private.current_membership_role(organization_id)) = 'admin'
      and role = 'member'
    )
  )
);

create policy organization_memberships_update
on app.organization_memberships
for update
to app_api
using ((select app_private.current_membership_role(organization_id)) = 'owner')
with check ((select app_private.current_membership_role(organization_id)) = 'owner');

create policy organization_memberships_delete
on app.organization_memberships
for delete
to app_api
using (
  user_id = (select auth.uid())
  or (select app_private.current_membership_role(organization_id)) = 'owner'
  or (
    (select app_private.current_membership_role(organization_id)) = 'admin'
    and role = 'member'
  )
);
