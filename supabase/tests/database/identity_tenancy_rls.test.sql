begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to app_api;
grant execute on all functions in schema extensions to app_api;
set local search_path = public, extensions;

select plan(30);

select has_table('app', 'user_profiles', 'user profiles table exists');
select has_table('app', 'organizations', 'organizations table exists');
select has_table(
  'app',
  'organization_memberships',
  'organization memberships table exists'
);
select ok(
  (
    select bool_and(class.relrowsecurity and class.relforcerowsecurity)
    from pg_catalog.pg_class as class
    inner join pg_catalog.pg_namespace as namespace on namespace.oid = class.relnamespace
    where namespace.nspname = 'app'
      and class.relname in ('user_profiles', 'organizations', 'organization_memberships')
  ),
  'all application tables enable and force RLS'
);
select ok(
  (
    select bool_and(not role.rolsuper and not role.rolbypassrls)
    from pg_catalog.pg_roles as role
    where role.rolname in ('api_login', 'app_api')
  ),
  'runtime roles cannot bypass RLS'
);
select ok(
  not pg_catalog.has_table_privilege('api_login', 'app.organizations', 'select'),
  'the login role has no direct organization privileges'
);
select ok(
  pg_catalog.has_table_privilege('app_api', 'app.organizations', 'select'),
  'the assumed application role has explicit organization privileges'
);

insert into auth.users (
  id,
  email,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at
)
values
  (
    '10000000-0000-0000-0000-000000000001',
    'owner-a@example.test',
    '{}',
    '{"display_name":"Owner A"}',
    now(),
    now()
  ),
  (
    '10000000-0000-0000-0000-000000000002',
    'owner-b@example.test',
    '{}',
    '{"display_name":"Owner B"}',
    now(),
    now()
  ),
  (
    '10000000-0000-0000-0000-000000000003',
    'admin-a@example.test',
    '{}',
    '{"display_name":"Admin A"}',
    now(),
    now()
  ),
  (
    '10000000-0000-0000-0000-000000000004',
    'member-a@example.test',
    '{}',
    '{"display_name":"Member A"}',
    now(),
    now()
  ),
  (
    '10000000-0000-0000-0000-000000000005',
    'unassigned@example.test',
    '{}',
    '{"display_name":"Unassigned"}',
    now(),
    now()
  );

select is(
  (select count(*) from app.user_profiles),
  5::bigint,
  'the Auth trigger creates safe application profiles'
);

insert into app.organizations (id, name, created_by_user_id)
values
  (
    '20000000-0000-0000-0000-000000000001',
    'Organization A',
    '10000000-0000-0000-0000-000000000001'
  ),
  (
    '20000000-0000-0000-0000-000000000002',
    'Organization B',
    '10000000-0000-0000-0000-000000000002'
  );

insert into app.organization_memberships (id, organization_id, user_id, role)
values
  (
    '30000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    'owner'
  ),
  (
    '30000000-0000-0000-0000-000000000002',
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000003',
    'admin'
  ),
  (
    '30000000-0000-0000-0000-000000000003',
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000004',
    'member'
  ),
  (
    '30000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000002',
    '10000000-0000-0000-0000-000000000002',
    'owner'
  );

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
select results_eq(
  $$ select id from app.organizations order by id $$,
  $$ values ('20000000-0000-0000-0000-000000000001'::uuid) $$,
  'an owner sees only their organization'
);
select is(
  (select count(*) from app.organization_memberships),
  3::bigint,
  'an owner sees only memberships in their organization'
);
select is(
  (select count(*) from app.user_profiles),
  3::bigint,
  'a user sees only their own and co-members profiles'
);
reset role;

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000002","role":"authenticated"}',
  true
);
select results_eq(
  $$ select id from app.organizations order by id $$,
  $$ values ('20000000-0000-0000-0000-000000000002'::uuid) $$,
  'a second owner cannot read the first tenant'
);
update app.organizations
set name = 'Cross-tenant update'
where id = '20000000-0000-0000-0000-000000000001';
reset role;
select is(
  (
    select name
    from app.organizations
    where id = '20000000-0000-0000-0000-000000000001'
  ),
  'Organization A',
  'a cross-tenant update affects no row'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000003","role":"authenticated"}',
  true
);
update app.organizations
set name = 'Organization A Updated'
where id = '20000000-0000-0000-0000-000000000001';
update app.organization_memberships
set role = 'admin'
where id = '30000000-0000-0000-0000-000000000003';
reset role;
select is(
  (
    select name
    from app.organizations
    where id = '20000000-0000-0000-0000-000000000001'
  ),
  'Organization A Updated',
  'an admin can update organization settings'
);
select is(
  (
    select role
    from app.organization_memberships
    where id = '30000000-0000-0000-0000-000000000003'
  ),
  'member',
  'an admin cannot change membership roles'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
update app.organization_memberships
set role = 'admin'
where id = '30000000-0000-0000-0000-000000000003';
reset role;
select is(
  (
    select role
    from app.organization_memberships
    where id = '30000000-0000-0000-0000-000000000003'
  ),
  'admin',
  'an owner can change membership roles'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
insert into app.organizations (id, name, created_by_user_id)
values (
  '20000000-0000-0000-0000-000000000003',
  'Organization C',
  '10000000-0000-0000-0000-000000000001'
);
insert into app.organization_memberships (id, organization_id, user_id, role)
values (
  '30000000-0000-0000-0000-000000000005',
  '20000000-0000-0000-0000-000000000003',
  '10000000-0000-0000-0000-000000000001',
  'owner'
);
reset role;
select is(
  (
    select count(*)
    from app.organization_memberships
    where organization_id = '20000000-0000-0000-0000-000000000003'
      and role = 'owner'
  ),
  1::bigint,
  'an authenticated creator can atomically bootstrap ownership'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
select throws_ok(
  $$
    insert into app.organizations (id, name, created_by_user_id)
    values (
      '20000000-0000-0000-0000-000000000004',
      'Forged Organization',
      '10000000-0000-0000-0000-000000000002'
    )
  $$,
  '42501',
  'new row violates row-level security policy for table "organizations"',
  'organization creation cannot forge another creator'
);
reset role;

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
insert into app.organization_memberships (organization_id, user_id, role)
values (
  '20000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000002',
  'member'
);
reset role;
select is(
  (
    select role
    from app.organization_memberships
    where organization_id = '20000000-0000-0000-0000-000000000001'
      and user_id = '10000000-0000-0000-0000-000000000002'
  ),
  'member',
  'an owner can add an existing user by UUID'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000003","role":"authenticated"}',
  true
);
select throws_ok(
  $$
    insert into app.organization_memberships (organization_id, user_id, role)
    values (
      '20000000-0000-0000-0000-000000000001',
      '10000000-0000-0000-0000-000000000005',
      'owner'
    )
  $$,
  '42501',
  'new row violates row-level security policy for table "organization_memberships"',
  'an admin cannot grant ownership'
);
insert into app.organization_memberships (organization_id, user_id, role)
values (
  '20000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000005',
  'member'
);
reset role;
select is(
  (
    select role
    from app.organization_memberships
    where organization_id = '20000000-0000-0000-0000-000000000001'
      and user_id = '10000000-0000-0000-0000-000000000005'
  ),
  'member',
  'an admin can add a member'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000002","role":"authenticated"}',
  true
);
select throws_ok(
  $$
    update app.organization_memberships
    set role = 'member'
    where id = '30000000-0000-0000-0000-000000000004'
  $$,
  '23514',
  'organization must retain at least one owner',
  'the last owner cannot be demoted'
);
reset role;

set local role app_api;
select set_config('request.jwt.claims', '{}', true);
select is(
  (select count(*) from app.organizations),
  0::bigint,
  'missing identity claims deny all organization rows'
);
reset role;

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
update app.user_profiles
set display_name = 'Owner A Updated'
where user_id = '10000000-0000-0000-0000-000000000001';
reset role;
select is(
  (
    select display_name
    from app.user_profiles
    where user_id = '10000000-0000-0000-0000-000000000001'
  ),
  'Owner A Updated',
  'a user can update their own profile'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"10000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
update app.user_profiles
set display_name = 'Forged Owner B'
where user_id = '10000000-0000-0000-0000-000000000002';
reset role;
select is(
  (
    select display_name
    from app.user_profiles
    where user_id = '10000000-0000-0000-0000-000000000002'
  ),
  'Owner B',
  'a user cannot update a foreign profile'
);

select has_index(
  'app',
  'organization_memberships',
  'organization_memberships_user_id_idx',
  'membership lookup by user is indexed'
);
select has_index(
  'app',
  'organization_memberships',
  'organization_memberships_organization_role_idx',
  'membership role checks are indexed by organization'
);
select col_is_pk('app', 'organizations', 'id', 'organizations use UUID primary keys');
select col_is_pk(
  'app',
  'organization_memberships',
  'id',
  'memberships use UUID primary keys'
);
select ok(
  not pg_catalog.has_schema_privilege('anon', 'app', 'usage')
    and not pg_catalog.has_schema_privilege('authenticated', 'app', 'usage'),
  'Supabase Data API roles cannot access the application schema'
);

select * from finish();
rollback;
