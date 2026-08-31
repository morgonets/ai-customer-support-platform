-- M2 organization-scoped knowledge-base foundation.
--
-- Recovery: this migration is additive and can be removed before knowledge data exists by dropping
-- its policies, functions, triggers, and tables in dependency order. After an uploaded file or
-- knowledge row exists, prefer a forward migration. A schema rollback does not delete filesystem
-- objects and must not run until those objects have been inventoried and recovered or removed.

create table app.knowledge_sources (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references app.organizations (id) on delete restrict,
  kind text not null,
  title text not null,
  description text,
  created_by_user_id uuid references auth.users (id) on delete set null,
  updated_by_user_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint knowledge_sources_kind_valid check (kind in ('article', 'document')),
  constraint knowledge_sources_title_valid check (
    title = btrim(title)
    and char_length(title) between 1 and 200
  ),
  constraint knowledge_sources_description_valid check (
    description is null
    or (
      description = btrim(description)
      and char_length(description) between 1 and 2000
    )
  ),
  constraint knowledge_sources_organization_id_id_kind_unique
    unique (organization_id, id, kind)
);

create table app.knowledge_source_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  source_id uuid not null,
  kind text not null,
  version_number integer not null,
  is_current boolean not null default true,
  status text not null,
  raw_text text,
  normalized_text text,
  normalization_version smallint not null default 1,
  locator_map jsonb,
  original_filename text,
  media_type text,
  size_bytes bigint,
  sha256 text,
  storage_key text,
  extractor_name text,
  extractor_version text,
  processing_attempts smallint not null default 0,
  processing_started_at timestamptz,
  processed_at timestamptz,
  failure_code text,
  failure_message text,
  created_by_user_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint knowledge_source_versions_source_fk
    foreign key (organization_id, source_id, kind)
    references app.knowledge_sources (organization_id, id, kind)
    on delete cascade,
  constraint knowledge_source_versions_organization_id_id_unique
    unique (organization_id, id),
  constraint knowledge_source_versions_number_unique
    unique (organization_id, source_id, version_number),
  constraint knowledge_source_versions_number_valid check (version_number > 0),
  constraint knowledge_source_versions_kind_valid check (kind in ('article', 'document')),
  constraint knowledge_source_versions_status_valid
    check (status in ('processing', 'ready', 'failed')),
  constraint knowledge_source_versions_normalization_version_valid
    check (normalization_version > 0),
  constraint knowledge_source_versions_processing_attempts_valid
    check (processing_attempts >= 0),
  constraint knowledge_source_versions_raw_text_size_valid
    check (raw_text is null or char_length(raw_text) between 1 and 500000),
  constraint knowledge_source_versions_normalized_text_size_valid
    check (normalized_text is null or char_length(normalized_text) between 1 and 2000000),
  constraint knowledge_source_versions_locator_map_valid check (
    locator_map is null or jsonb_typeof(locator_map) = 'object'
  ),
  constraint knowledge_source_versions_filename_valid check (
    original_filename is null
    or (
      original_filename = btrim(original_filename)
      and char_length(original_filename) between 1 and 255
    )
  ),
  constraint knowledge_source_versions_media_type_valid check (
    media_type is null
    or media_type in ('text/plain', 'text/markdown', 'application/pdf')
  ),
  constraint knowledge_source_versions_size_valid
    check (size_bytes is null or size_bytes between 1 and 10485760),
  constraint knowledge_source_versions_sha256_valid
    check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
  constraint knowledge_source_versions_storage_key_valid check (
    storage_key is null
    or storage_key = organization_id::text || '/' || source_id::text || '/' || id::text || '/content'
  ),
  constraint knowledge_source_versions_extractor_name_valid check (
    extractor_name is null or char_length(extractor_name) between 1 and 100
  ),
  constraint knowledge_source_versions_extractor_version_valid check (
    extractor_version is null or char_length(extractor_version) between 1 and 100
  ),
  constraint knowledge_source_versions_failure_code_valid check (
    failure_code is null or char_length(failure_code) between 1 and 100
  ),
  constraint knowledge_source_versions_failure_message_valid check (
    failure_message is null or char_length(failure_message) between 1 and 500
  ),
  constraint knowledge_source_versions_payload_valid check (
    (
      kind = 'article'
      and raw_text is not null
      and original_filename is null
      and media_type is null
      and size_bytes is null
      and sha256 is null
      and storage_key is null
      and status = 'ready'
      and processing_attempts = 0
    )
    or (
      kind = 'document'
      and raw_text is null
      and original_filename is not null
      and media_type is not null
      and size_bytes is not null
      and sha256 is not null
      and storage_key is not null
      and processing_attempts >= 1
    )
  ),
  constraint knowledge_source_versions_state_valid check (
    (
      status = 'processing'
      and normalized_text is null
      and locator_map is null
      and processing_started_at is not null
      and processed_at is null
      and failure_code is null
      and failure_message is null
    )
    or (
      status = 'ready'
      and normalized_text is not null
      and locator_map is not null
      and processed_at is not null
      and failure_code is null
      and failure_message is null
    )
    or (
      status = 'failed'
      and normalized_text is null
      and locator_map is null
      and processed_at is not null
      and failure_code is not null
      and failure_message is not null
    )
  )
);

create index knowledge_sources_organization_created_idx
  on app.knowledge_sources (organization_id, created_at desc, id desc);
create index knowledge_sources_organization_kind_created_idx
  on app.knowledge_sources (organization_id, kind, created_at desc, id desc);
create unique index knowledge_source_versions_current_unique_idx
  on app.knowledge_source_versions (organization_id, source_id)
  where is_current;
create index knowledge_source_versions_organization_status_current_idx
  on app.knowledge_source_versions (organization_id, status, source_id)
  where is_current;
create unique index knowledge_source_versions_storage_key_unique_idx
  on app.knowledge_source_versions (storage_key)
  where storage_key is not null;

create trigger knowledge_sources_set_updated_at
before update on app.knowledge_sources
for each row execute function app_private.set_updated_at();

create trigger knowledge_source_versions_set_updated_at
before update on app.knowledge_source_versions
for each row execute function app_private.set_updated_at();

create function app_private.prevent_ready_knowledge_version_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if old.status = 'ready' and (
    new.organization_id is distinct from old.organization_id
    or new.source_id is distinct from old.source_id
    or new.kind is distinct from old.kind
    or new.version_number is distinct from old.version_number
    or new.status is distinct from old.status
    or new.raw_text is distinct from old.raw_text
    or new.normalized_text is distinct from old.normalized_text
    or new.normalization_version is distinct from old.normalization_version
    or new.locator_map is distinct from old.locator_map
    or new.original_filename is distinct from old.original_filename
    or new.media_type is distinct from old.media_type
    or new.size_bytes is distinct from old.size_bytes
    or new.sha256 is distinct from old.sha256
    or new.storage_key is distinct from old.storage_key
    or new.extractor_name is distinct from old.extractor_name
    or new.extractor_version is distinct from old.extractor_version
    or new.processing_attempts is distinct from old.processing_attempts
    or new.processing_started_at is distinct from old.processing_started_at
    or new.processed_at is distinct from old.processed_at
    or new.failure_code is distinct from old.failure_code
    or new.failure_message is distinct from old.failure_message
  ) then
    raise exception using
      errcode = '23514',
      message = 'ready knowledge source versions are immutable';
  end if;
  return new;
end;
$$;

create trigger knowledge_source_versions_ready_immutable
before update on app.knowledge_source_versions
for each row execute function app_private.prevent_ready_knowledge_version_mutation();

create function app_private.knowledge_file_objects(
  target_organization_id uuid,
  target_source_id uuid
)
returns table (
  version_id uuid,
  storage_key text,
  original_filename text,
  media_type text,
  size_bytes bigint
)
language sql
stable
security definer
set search_path = ''
as $$
  select version.id,
         version.storage_key,
         version.original_filename,
         version.media_type,
         version.size_bytes
  from app.knowledge_source_versions as version
  where version.organization_id = target_organization_id
    and version.source_id = target_source_id
    and version.kind = 'document'
    and (select app_private.current_membership_role(target_organization_id)) in ('owner', 'admin')
  order by version.version_number desc
$$;

revoke execute on function app_private.prevent_ready_knowledge_version_mutation()
  from public, anon, authenticated, service_role;
revoke execute on function app_private.knowledge_file_objects(uuid, uuid)
  from public, anon, authenticated, service_role;
grant execute on function app_private.knowledge_file_objects(uuid, uuid) to app_api;

revoke all on app.knowledge_sources from public, anon, authenticated, service_role;
revoke all on app.knowledge_source_versions from public, anon, authenticated, service_role;

grant select, insert, delete on app.knowledge_sources to app_api;
grant update (title, description, updated_by_user_id) on app.knowledge_sources to app_api;

grant select (
  id,
  organization_id,
  source_id,
  kind,
  version_number,
  is_current,
  status,
  raw_text,
  normalized_text,
  normalization_version,
  locator_map,
  original_filename,
  media_type,
  size_bytes,
  sha256,
  extractor_name,
  extractor_version,
  processing_attempts,
  processing_started_at,
  processed_at,
  failure_code,
  failure_message,
  created_by_user_id,
  created_at,
  updated_at
) on app.knowledge_source_versions to app_api;
grant insert on app.knowledge_source_versions to app_api;
grant update (
  is_current,
  status,
  normalized_text,
  normalization_version,
  locator_map,
  extractor_name,
  extractor_version,
  processing_attempts,
  processing_started_at,
  processed_at,
  failure_code,
  failure_message
) on app.knowledge_source_versions to app_api;

alter table app.knowledge_sources enable row level security;
alter table app.knowledge_sources force row level security;
alter table app.knowledge_source_versions enable row level security;
alter table app.knowledge_source_versions force row level security;

create policy knowledge_sources_select
on app.knowledge_sources
for select
to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);

create policy knowledge_sources_insert
on app.knowledge_sources
for insert
to app_api
with check (
  (select app_private.current_membership_role(organization_id)) in ('owner', 'admin')
  and created_by_user_id = (select auth.uid())
  and updated_by_user_id = (select auth.uid())
);

create policy knowledge_sources_update
on app.knowledge_sources
for update
to app_api
using ((select app_private.current_membership_role(organization_id)) in ('owner', 'admin'))
with check (
  (select app_private.current_membership_role(organization_id)) in ('owner', 'admin')
  and updated_by_user_id = (select auth.uid())
);

create policy knowledge_sources_delete
on app.knowledge_sources
for delete
to app_api
using ((select app_private.current_membership_role(organization_id)) in ('owner', 'admin'));

create policy knowledge_source_versions_select
on app.knowledge_source_versions
for select
to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);

create policy knowledge_source_versions_insert
on app.knowledge_source_versions
for insert
to app_api
with check (
  (select app_private.current_membership_role(organization_id)) in ('owner', 'admin')
  and created_by_user_id = (select auth.uid())
);

create policy knowledge_source_versions_update
on app.knowledge_source_versions
for update
to app_api
using ((select app_private.current_membership_role(organization_id)) in ('owner', 'admin'))
with check ((select app_private.current_membership_role(organization_id)) in ('owner', 'admin'));
