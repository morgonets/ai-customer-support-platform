-- M3 tenant-scoped retrieval and grounded-answer foundation.
--
-- Recovery: this migration is additive. Before RAG data exists, remove its policies, functions,
-- tables, roles, and vector extension objects in dependency order. After indexing begins, prefer a
-- forward migration so active-generation lineage and citation identities remain auditable.

create extension if not exists vector with schema extensions;

do $$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'app_rag_worker') then
    create role app_rag_worker
      nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'rag_worker_login') then
    create role rag_worker_login
      login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  end if;
end
$$;

alter role app_rag_worker noinherit;
alter role rag_worker_login noinherit;
grant app_rag_worker to rag_worker_login;
grant app_rag_worker to postgres;
grant usage on schema app, app_private, extensions to app_rag_worker;
grant usage on schema extensions to app_api;

alter table app.knowledge_source_versions
  add constraint knowledge_source_versions_organization_source_id_unique
  unique (organization_id, source_id, id);

create table app.rag_embedding_profiles (
  id uuid primary key,
  profile_key text not null unique,
  fingerprint text not null unique,
  provider text not null,
  model text not null,
  model_revision text,
  dimensions integer not null,
  distance_metric text not null default 'cosine',
  document_input_version smallint not null default 1,
  query_input_version smallint not null default 1,
  created_at timestamptz not null default now(),
  constraint rag_embedding_profiles_id_dimensions_unique unique (id, dimensions),
  constraint rag_embedding_profiles_key_valid
    check (profile_key ~ '^[a-z0-9][a-z0-9_-]{0,99}$'),
  constraint rag_embedding_profiles_fingerprint_valid
    check (fingerprint ~ '^[0-9a-f]{64}$'),
  constraint rag_embedding_profiles_provider_valid check (char_length(provider) between 1 and 100),
  constraint rag_embedding_profiles_model_valid check (char_length(model) between 1 and 200),
  constraint rag_embedding_profiles_revision_valid
    check (model_revision is null or char_length(model_revision) between 1 and 200),
  constraint rag_embedding_profiles_dimensions_valid check (dimensions between 1 and 16000),
  constraint rag_embedding_profiles_distance_valid check (distance_metric = 'cosine'),
  constraint rag_embedding_profiles_input_versions_valid
    check (document_input_version > 0 and query_input_version > 0)
);

insert into app.rag_embedding_profiles (
  id, profile_key, fingerprint, provider, model, model_revision, dimensions
)
values
  (
    '70000000-0000-0000-0000-000000000001',
    'deterministic-local-v1',
    encode(extensions.digest(
      convert_to('deterministic|hash-v1|1536|document-v1|query-v1', 'utf8'), 'sha256'
    ), 'hex'),
    'deterministic',
    'hash-v1',
    '1',
    1536
  ),
  (
    '70000000-0000-0000-0000-000000000002',
    'openai-text-embedding-3-small-1536-v1',
    encode(extensions.digest(
      convert_to('openai|text-embedding-3-small|1536|document-v1|query-v1', 'utf8'), 'sha256'
    ), 'hex'),
    'openai',
    'text-embedding-3-small',
    null,
    1536
  );

create table app.organization_rag_settings (
  organization_id uuid primary key references app.organizations (id) on delete cascade,
  active_profile_id uuid not null references app.rag_embedding_profiles (id) on delete restrict,
  staging_profile_id uuid references app.rag_embedding_profiles (id) on delete restrict,
  updated_by_user_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organization_rag_settings_profiles_distinct
    check (staging_profile_id is null or staging_profile_id <> active_profile_id)
);

create table app.knowledge_chunk_sets (
  id uuid primary key,
  organization_id uuid not null,
  source_id uuid not null,
  knowledge_source_version_id uuid not null,
  chunker_name text not null,
  chunker_version text not null,
  chunker_config jsonb not null,
  chunker_fingerprint text not null,
  normalization_version smallint not null,
  normalized_content_sha256 text not null,
  chunk_count integer not null,
  created_at timestamptz not null default now(),
  constraint knowledge_chunk_sets_version_fk
    foreign key (organization_id, source_id, knowledge_source_version_id)
    references app.knowledge_source_versions (organization_id, source_id, id)
    on delete cascade,
  constraint knowledge_chunk_sets_lineage_unique
    unique (organization_id, source_id, knowledge_source_version_id, id),
  constraint knowledge_chunk_sets_fingerprint_unique
    unique (organization_id, knowledge_source_version_id, chunker_fingerprint),
  constraint knowledge_chunk_sets_names_valid check (
    char_length(chunker_name) between 1 and 100
    and char_length(chunker_version) between 1 and 100
  ),
  constraint knowledge_chunk_sets_config_valid check (jsonb_typeof(chunker_config) = 'object'),
  constraint knowledge_chunk_sets_hashes_valid check (
    chunker_fingerprint ~ '^[0-9a-f]{64}$'
    and normalized_content_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint knowledge_chunk_sets_values_valid
    check (normalization_version > 0 and chunk_count > 0)
);

create table app.knowledge_chunks (
  id uuid primary key,
  organization_id uuid not null,
  source_id uuid not null,
  knowledge_source_version_id uuid not null,
  chunk_set_id uuid not null,
  ordinal integer not null,
  content text not null,
  start_char integer not null,
  end_char integer not null,
  content_sha256 text not null,
  locator jsonb not null,
  search_vector tsvector generated always as (to_tsvector('simple', content)) stored,
  created_at timestamptz not null default now(),
  constraint knowledge_chunks_set_fk
    foreign key (organization_id, source_id, knowledge_source_version_id, chunk_set_id)
    references app.knowledge_chunk_sets (
      organization_id, source_id, knowledge_source_version_id, id
    ) on delete cascade,
  constraint knowledge_chunks_lineage_unique unique (
    organization_id, source_id, knowledge_source_version_id, chunk_set_id, id
  ),
  constraint knowledge_chunks_lineage_id_unique unique (
    organization_id, source_id, knowledge_source_version_id, id
  ),
  constraint knowledge_chunks_ordinal_unique unique (organization_id, chunk_set_id, ordinal),
  constraint knowledge_chunks_ordinal_valid check (ordinal >= 0),
  constraint knowledge_chunks_bounds_valid check (start_char >= 0 and end_char > start_char),
  constraint knowledge_chunks_content_valid check (char_length(content) between 1 and 2000),
  constraint knowledge_chunks_hash_valid check (content_sha256 ~ '^[0-9a-f]{64}$'),
  constraint knowledge_chunks_locator_valid check (jsonb_typeof(locator) = 'object')
);

create table app.knowledge_index_generations (
  id uuid primary key,
  organization_id uuid not null,
  source_id uuid not null,
  knowledge_source_version_id uuid not null,
  embedding_profile_id uuid not null references app.rag_embedding_profiles (id) on delete restrict,
  chunk_set_id uuid,
  generation_number integer not null,
  status text not null default 'queued',
  is_active boolean not null default false,
  requested_by_user_id uuid references auth.users (id) on delete set null,
  request_id uuid,
  attempt_count smallint not null default 0,
  available_at timestamptz not null default now(),
  lease_token uuid,
  lease_expires_at timestamptz,
  worker_id text,
  expected_chunk_count integer,
  embedded_chunk_count integer,
  provider_input_tokens integer,
  failure_code text,
  failure_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint knowledge_index_generations_version_fk
    foreign key (organization_id, source_id, knowledge_source_version_id)
    references app.knowledge_source_versions (organization_id, source_id, id)
    on delete cascade,
  constraint knowledge_index_generations_chunk_set_fk
    foreign key (organization_id, source_id, knowledge_source_version_id, chunk_set_id)
    references app.knowledge_chunk_sets (
      organization_id, source_id, knowledge_source_version_id, id
    ) on delete restrict,
  constraint knowledge_index_generations_lineage_unique
    unique (organization_id, source_id, knowledge_source_version_id, id),
  constraint knowledge_index_generations_profile_lineage_unique
    unique (organization_id, source_id, knowledge_source_version_id, id, embedding_profile_id),
  constraint knowledge_index_generations_number_unique
    unique (organization_id, source_id, embedding_profile_id, generation_number),
  constraint knowledge_index_generations_number_valid check (generation_number > 0),
  constraint knowledge_index_generations_status_valid
    check (status in ('queued', 'processing', 'ready', 'failed', 'cancelled')),
  constraint knowledge_index_generations_attempt_valid check (attempt_count >= 0),
  constraint knowledge_index_generations_worker_valid
    check (worker_id is null or char_length(worker_id) between 1 and 100),
  constraint knowledge_index_generations_counts_valid check (
    (expected_chunk_count is null or expected_chunk_count > 0)
    and (embedded_chunk_count is null or embedded_chunk_count >= 0)
    and (provider_input_tokens is null or provider_input_tokens >= 0)
  ),
  constraint knowledge_index_generations_failure_valid check (
    (failure_code is null or char_length(failure_code) between 1 and 100)
    and (failure_message is null or char_length(failure_message) between 1 and 500)
  ),
  constraint knowledge_index_generations_active_valid check (not is_active or status = 'ready'),
  constraint knowledge_index_generations_lease_valid check (
    (status = 'processing' and lease_token is not null and lease_expires_at is not null
      and worker_id is not null and started_at is not null)
    or (status <> 'processing' and lease_token is null and lease_expires_at is null)
  ),
  constraint knowledge_index_generations_ready_valid check (
    status <> 'ready'
    or (
      chunk_set_id is not null
      and expected_chunk_count is not null
      and embedded_chunk_count = expected_chunk_count
      and completed_at is not null
      and failure_code is null
      and failure_message is null
    )
  )
);

create table app.knowledge_chunk_embeddings (
  organization_id uuid not null,
  source_id uuid not null,
  knowledge_source_version_id uuid not null,
  generation_id uuid not null,
  chunk_id uuid not null,
  embedding_profile_id uuid not null references app.rag_embedding_profiles (id) on delete restrict,
  embedding_dimensions integer not null,
  embedding extensions.vector not null,
  created_at timestamptz not null default now(),
  primary key (organization_id, generation_id, chunk_id),
  constraint knowledge_chunk_embeddings_generation_fk
    foreign key (
      organization_id, source_id, knowledge_source_version_id, generation_id, embedding_profile_id
    )
    references app.knowledge_index_generations (
      organization_id, source_id, knowledge_source_version_id, id, embedding_profile_id
    ) on delete cascade,
  constraint knowledge_chunk_embeddings_chunk_fk
    foreign key (organization_id, source_id, knowledge_source_version_id, chunk_id)
    references app.knowledge_chunks (
      organization_id, source_id, knowledge_source_version_id, id
    ) on delete cascade,
  constraint knowledge_chunk_embeddings_profile_dimensions_fk
    foreign key (embedding_profile_id, embedding_dimensions)
    references app.rag_embedding_profiles (id, dimensions) on delete restrict,
  constraint knowledge_chunk_embeddings_dimensions_valid check (
    embedding_dimensions between 1 and 16000
    and extensions.vector_dims(embedding) = embedding_dimensions
  ),
  constraint knowledge_chunk_embeddings_nonzero check (extensions.vector_norm(embedding) > 0)
);

create unique index knowledge_index_generations_active_source_idx
  on app.knowledge_index_generations (organization_id, source_id)
  where is_active;
create index knowledge_index_generations_queue_idx
  on app.knowledge_index_generations (available_at, created_at, id)
  where status in ('queued', 'processing');
create index knowledge_index_generations_profile_idx
  on app.knowledge_index_generations (organization_id, embedding_profile_id, status, source_id);
create index knowledge_chunks_version_offsets_idx
  on app.knowledge_chunks (organization_id, knowledge_source_version_id, start_char, ordinal);
create index knowledge_chunks_search_idx on app.knowledge_chunks using gin (search_vector);
create index knowledge_chunk_embeddings_tenant_generation_idx
  on app.knowledge_chunk_embeddings (organization_id, generation_id, chunk_id);
create index knowledge_chunk_embeddings_hnsw_1536_idx
  on app.knowledge_chunk_embeddings
  using hnsw ((embedding::extensions.vector(1536)) extensions.vector_cosine_ops)
  where embedding_dimensions = 1536;

create trigger organization_rag_settings_set_updated_at
before update on app.organization_rag_settings
for each row execute function app_private.set_updated_at();
create trigger knowledge_index_generations_set_updated_at
before update on app.knowledge_index_generations
for each row execute function app_private.set_updated_at();

create function app_private.prevent_rag_immutable_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = '23514', message = 'ready RAG artifacts are immutable';
end;
$$;

create trigger rag_embedding_profiles_immutable
before update on app.rag_embedding_profiles
for each row execute function app_private.prevent_rag_immutable_mutation();
create trigger knowledge_chunk_sets_immutable
before update on app.knowledge_chunk_sets
for each row execute function app_private.prevent_rag_immutable_mutation();
create trigger knowledge_chunks_immutable
before update on app.knowledge_chunks
for each row execute function app_private.prevent_rag_immutable_mutation();
create trigger knowledge_chunk_embeddings_immutable
before update on app.knowledge_chunk_embeddings
for each row execute function app_private.prevent_rag_immutable_mutation();

create function app_private.rag_worker_has_lease(
  target_generation_id uuid,
  target_organization_id uuid
)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
    from app.knowledge_index_generations as generation
    where generation.id = target_generation_id
      and generation.organization_id = target_organization_id
      and generation.status = 'processing'
      and generation.lease_token::text = current_setting('app.rag_lease_token', true)
      and generation.lease_expires_at > now()
  )
$$;

create function app_private.rag_worker_has_version_lease(
  target_organization_id uuid,
  target_source_id uuid,
  target_version_id uuid
)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
    from app.knowledge_index_generations as generation
    where generation.organization_id = target_organization_id
      and generation.source_id = target_source_id
      and generation.knowledge_source_version_id = target_version_id
      and generation.status = 'processing'
      and generation.lease_token::text = current_setting('app.rag_lease_token', true)
      and generation.lease_expires_at > now()
  )
$$;

create function app_private.claim_rag_generation(target_worker_id text, lease_seconds integer)
returns table (
  generation_id uuid,
  organization_id uuid,
  source_id uuid,
  knowledge_source_version_id uuid,
  embedding_profile_id uuid,
  profile_key text,
  provider text,
  model text,
  model_revision text,
  dimensions integer,
  attempt_count smallint,
  lease_token uuid,
  normalized_text text,
  normalization_version smallint,
  locator_map jsonb
)
language plpgsql security definer set search_path = '' as $$
declare
  claimed_id uuid;
  claimed_token uuid := gen_random_uuid();
begin
  if target_worker_id is null or char_length(target_worker_id) not between 1 and 100
     or lease_seconds not between 30 and 3600 then
    raise exception using errcode = '22023', message = 'invalid RAG worker lease request';
  end if;

  select candidate.id into claimed_id
  from app.knowledge_index_generations as candidate
  where (
      (candidate.status = 'queued' and candidate.available_at <= now())
      or (candidate.status = 'processing' and candidate.lease_expires_at <= now())
    )
    and exists (
      select 1
      from app.knowledge_source_versions as candidate_version
      where candidate_version.organization_id = candidate.organization_id
        and candidate_version.source_id = candidate.source_id
        and candidate_version.id = candidate.knowledge_source_version_id
        and candidate_version.status = 'ready'
    )
  order by candidate.available_at, candidate.created_at, candidate.id
  for update skip locked
  limit 1;

  if claimed_id is null then
    return;
  end if;

  update app.knowledge_index_generations as generation
  set status = 'processing',
      attempt_count = generation.attempt_count + 1,
      lease_token = claimed_token,
      lease_expires_at = now() + make_interval(secs => lease_seconds),
      worker_id = target_worker_id,
      started_at = coalesce(generation.started_at, now()),
      completed_at = null,
      failure_code = null,
      failure_message = null
  where generation.id = claimed_id;

  return query
  select generation.id,
         generation.organization_id,
         generation.source_id,
         generation.knowledge_source_version_id,
         generation.embedding_profile_id,
         profile.profile_key,
         profile.provider,
         profile.model,
         profile.model_revision,
         profile.dimensions,
         generation.attempt_count,
         claimed_token,
         version.normalized_text,
         version.normalization_version,
         version.locator_map
  from app.knowledge_index_generations as generation
  inner join app.rag_embedding_profiles as profile on profile.id = generation.embedding_profile_id
  inner join app.knowledge_source_versions as version
    on version.organization_id = generation.organization_id
   and version.source_id = generation.source_id
   and version.id = generation.knowledge_source_version_id
  where generation.id = claimed_id
    and version.status = 'ready';
end;
$$;

create function app_private.try_activate_staging_rag_profile(target_organization_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
  target_profile_id uuid;
begin
  select settings.staging_profile_id into target_profile_id
  from app.organization_rag_settings as settings
  where settings.organization_id = target_organization_id
  for update;

  if target_profile_id is null then
    return false;
  end if;

  if exists (
    select 1
    from app.knowledge_sources as source
    inner join app.knowledge_source_versions as version
      on version.organization_id = source.organization_id
     and version.source_id = source.id
     and version.is_current
     and version.status = 'ready'
    where source.organization_id = target_organization_id
      and not exists (
        select 1
        from app.knowledge_index_generations as generation
        where generation.organization_id = source.organization_id
          and generation.source_id = source.id
          and generation.knowledge_source_version_id = version.id
          and generation.embedding_profile_id = target_profile_id
          and generation.status = 'ready'
      )
  ) then
    return false;
  end if;

  perform 1
  from app.knowledge_index_generations
  where organization_id = target_organization_id
  for update;

  update app.knowledge_index_generations
  set is_active = false
  where organization_id = target_organization_id and is_active;

  update app.knowledge_index_generations as generation
  set is_active = true
  from (
    select distinct on (candidate.source_id) candidate.id
    from app.knowledge_index_generations as candidate
    inner join app.knowledge_source_versions as version
      on version.organization_id = candidate.organization_id
     and version.source_id = candidate.source_id
     and version.id = candidate.knowledge_source_version_id
     and version.is_current
     and version.status = 'ready'
    where candidate.organization_id = target_organization_id
      and candidate.embedding_profile_id = target_profile_id
      and candidate.status = 'ready'
    order by candidate.source_id, candidate.generation_number desc, candidate.id
  ) as selected
  where generation.id = selected.id;

  update app.organization_rag_settings
  set active_profile_id = target_profile_id,
      staging_profile_id = null
  where organization_id = target_organization_id;

  return true;
end;
$$;

create function app_private.complete_rag_generation(
  target_generation_id uuid,
  target_lease_token uuid,
  target_chunk_set_id uuid,
  target_expected_chunks integer,
  target_input_tokens integer
)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
  target app.knowledge_index_generations%rowtype;
  target_organization_id uuid;
  stored_chunks integer;
  stored_embeddings integer;
  active_profile uuid;
begin
  select generation.organization_id into target_organization_id
  from app.knowledge_index_generations as generation
  where generation.id = target_generation_id;

  if target_organization_id is null then
    raise exception using errcode = '55000', message = 'RAG generation lease is not active';
  end if;

  -- Every completion for an organization takes the same lock before touching a generation row.
  -- This serializes source/profile activation and avoids deadlocks between parallel workers.
  perform 1
  from app.organization_rag_settings
  where organization_id = target_organization_id
  for update;

  select * into target
  from app.knowledge_index_generations
  where id = target_generation_id and organization_id = target_organization_id
  for update;

  if target.id is null
     or target.status <> 'processing'
     or target.lease_token <> target_lease_token
     or target.lease_expires_at <= now() then
    raise exception using errcode = '55000', message = 'RAG generation lease is not active';
  end if;

  select count(*) into stored_chunks
  from app.knowledge_chunks
  where organization_id = target.organization_id and chunk_set_id = target_chunk_set_id;
  select count(*) into stored_embeddings
  from app.knowledge_chunk_embeddings as embedding
  inner join app.knowledge_chunks as chunk
    on chunk.organization_id = embedding.organization_id
   and chunk.source_id = embedding.source_id
   and chunk.knowledge_source_version_id = embedding.knowledge_source_version_id
   and chunk.id = embedding.chunk_id
   and chunk.chunk_set_id = target_chunk_set_id
  where embedding.organization_id = target.organization_id
    and embedding.generation_id = target.id
    and embedding.embedding_profile_id = target.embedding_profile_id;

  if target_expected_chunks <= 0
     or stored_chunks <> target_expected_chunks
     or stored_embeddings <> target_expected_chunks then
    raise exception using errcode = '23514', message = 'RAG generation is incomplete';
  end if;

  if not exists (
    select 1 from app.knowledge_source_versions as version
    where version.organization_id = target.organization_id
      and version.source_id = target.source_id
      and version.id = target.knowledge_source_version_id
      and version.status = 'ready'
      and version.is_current
  ) then
    update app.knowledge_index_generations
    set status = 'cancelled', lease_token = null, lease_expires_at = null,
        worker_id = null, completed_at = now(), is_active = false
    where id = target.id;
    return false;
  end if;

  select settings.active_profile_id into active_profile
  from app.organization_rag_settings as settings
  where settings.organization_id = target.organization_id;

  update app.knowledge_index_generations
  set status = 'ready',
      chunk_set_id = target_chunk_set_id,
      expected_chunk_count = target_expected_chunks,
      embedded_chunk_count = target_expected_chunks,
      provider_input_tokens = target_input_tokens,
      lease_token = null,
      lease_expires_at = null,
      worker_id = null,
      completed_at = now(),
      is_active = false
  where id = target.id;

  if active_profile = target.embedding_profile_id then
    perform 1
    from app.knowledge_index_generations
    where organization_id = target.organization_id and source_id = target.source_id
    for update;

    update app.knowledge_index_generations
    set is_active = false
    where organization_id = target.organization_id
      and source_id = target.source_id
      and is_active;
    update app.knowledge_index_generations set is_active = true where id = target.id;
  end if;

  perform app_private.try_activate_staging_rag_profile(target.organization_id);

  return true;
end;
$$;

create function app_private.fail_rag_generation(
  target_generation_id uuid,
  target_lease_token uuid,
  target_failure_code text,
  target_failure_message text,
  retry_at timestamptz default null
)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if char_length(target_failure_code) not between 1 and 100
     or char_length(target_failure_message) not between 1 and 500 then
    raise exception using errcode = '22023', message = 'invalid RAG failure details';
  end if;

  update app.knowledge_index_generations
  set status = case when retry_at is null then 'failed' else 'queued' end,
      available_at = coalesce(retry_at, available_at),
      lease_token = null,
      lease_expires_at = null,
      worker_id = null,
      completed_at = case when retry_at is null then now() else null end,
      failure_code = target_failure_code,
      failure_message = target_failure_message,
      is_active = false
  where id = target_generation_id
    and status = 'processing'
    and lease_token = target_lease_token;

  if not found then
    raise exception using errcode = '55000', message = 'RAG generation lease is not active';
  end if;
end;
$$;

revoke execute on function app_private.prevent_rag_immutable_mutation()
  from public, anon, authenticated, service_role;
revoke execute on function app_private.rag_worker_has_lease(uuid, uuid)
  from public, anon, authenticated, service_role;
revoke execute on function app_private.rag_worker_has_version_lease(uuid, uuid, uuid)
  from public, anon, authenticated, service_role;
revoke execute on function app_private.claim_rag_generation(text, integer)
  from public, anon, authenticated, service_role;
revoke execute on function app_private.try_activate_staging_rag_profile(uuid)
  from public, anon, authenticated, service_role;
revoke execute on function app_private.complete_rag_generation(uuid, uuid, uuid, integer, integer)
  from public, anon, authenticated, service_role;
revoke execute on function app_private.fail_rag_generation(uuid, uuid, text, text, timestamptz)
  from public, anon, authenticated, service_role;
grant execute on function app_private.claim_rag_generation(text, integer) to app_rag_worker;
grant execute on function app_private.rag_worker_has_lease(uuid, uuid) to app_rag_worker;
grant execute on function app_private.rag_worker_has_version_lease(uuid, uuid, uuid)
  to app_rag_worker;
grant execute on function app_private.complete_rag_generation(uuid, uuid, uuid, integer, integer)
  to app_rag_worker;
grant execute on function app_private.fail_rag_generation(uuid, uuid, text, text, timestamptz)
  to app_rag_worker;

revoke all on app.rag_embedding_profiles from public, anon, authenticated, service_role;
revoke all on app.organization_rag_settings from public, anon, authenticated, service_role;
revoke all on app.knowledge_chunk_sets from public, anon, authenticated, service_role;
revoke all on app.knowledge_chunks from public, anon, authenticated, service_role;
revoke all on app.knowledge_index_generations from public, anon, authenticated, service_role;
revoke all on app.knowledge_chunk_embeddings from public, anon, authenticated, service_role;

grant select on app.rag_embedding_profiles to app_api, app_rag_worker;
grant select, insert on app.organization_rag_settings to app_api;
grant update (staging_profile_id, updated_by_user_id)
  on app.organization_rag_settings to app_api;
grant select on app.knowledge_chunk_sets, app.knowledge_chunks,
  app.knowledge_index_generations, app.knowledge_chunk_embeddings to app_api;
grant insert on app.knowledge_index_generations to app_api;
grant update (status, available_at, failure_code, failure_message, completed_at)
  on app.knowledge_index_generations to app_api;
grant select, insert on app.knowledge_chunk_sets, app.knowledge_chunks to app_rag_worker;
grant select, insert, delete on app.knowledge_chunk_embeddings to app_rag_worker;

alter table app.organization_rag_settings enable row level security;
alter table app.organization_rag_settings force row level security;
alter table app.knowledge_chunk_sets enable row level security;
alter table app.knowledge_chunk_sets force row level security;
alter table app.knowledge_chunks enable row level security;
alter table app.knowledge_chunks force row level security;
alter table app.knowledge_index_generations enable row level security;
alter table app.knowledge_index_generations force row level security;
alter table app.knowledge_chunk_embeddings enable row level security;
alter table app.knowledge_chunk_embeddings force row level security;

create policy organization_rag_settings_select on app.organization_rag_settings
for select to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);
create policy organization_rag_settings_insert on app.organization_rag_settings
for insert to app_api
with check (
  (select app_private.current_membership_role(organization_id)) in ('owner', 'admin')
  and updated_by_user_id = (select auth.uid())
);
create policy organization_rag_settings_update on app.organization_rag_settings
for update to app_api
using ((select app_private.current_membership_role(organization_id)) in ('owner', 'admin'))
with check (
  (select app_private.current_membership_role(organization_id)) in ('owner', 'admin')
  and updated_by_user_id = (select auth.uid())
);

create policy knowledge_chunk_sets_select on app.knowledge_chunk_sets
for select to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);
create policy knowledge_chunks_select on app.knowledge_chunks
for select to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);
create policy knowledge_index_generations_select on app.knowledge_index_generations
for select to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);
create policy knowledge_index_generations_insert on app.knowledge_index_generations
for insert to app_api
with check (
  (select app_private.current_membership_role(organization_id)) in ('owner', 'admin')
  and requested_by_user_id = (select auth.uid())
);
create policy knowledge_index_generations_update on app.knowledge_index_generations
for update to app_api
using ((select app_private.current_membership_role(organization_id)) in ('owner', 'admin'))
with check ((select app_private.current_membership_role(organization_id)) in ('owner', 'admin'));
create policy knowledge_chunk_embeddings_select on app.knowledge_chunk_embeddings
for select to app_api
using ((select app_private.current_membership_role(organization_id)) is not null);

create policy knowledge_chunk_sets_worker_select on app.knowledge_chunk_sets
for select to app_rag_worker
using ((select app_private.rag_worker_has_version_lease(
  organization_id, source_id, knowledge_source_version_id
)));
create policy knowledge_chunk_sets_worker_insert on app.knowledge_chunk_sets
for insert to app_rag_worker
with check ((select app_private.rag_worker_has_version_lease(
  organization_id, source_id, knowledge_source_version_id
)));
create policy knowledge_chunks_worker_select on app.knowledge_chunks
for select to app_rag_worker
using ((select app_private.rag_worker_has_version_lease(
  organization_id, source_id, knowledge_source_version_id
)));
create policy knowledge_chunks_worker_insert on app.knowledge_chunks
for insert to app_rag_worker
with check ((select app_private.rag_worker_has_version_lease(
  organization_id, source_id, knowledge_source_version_id
)));
create policy knowledge_chunk_embeddings_worker_select on app.knowledge_chunk_embeddings
for select to app_rag_worker
using ((select app_private.rag_worker_has_lease(generation_id, organization_id)));
create policy knowledge_chunk_embeddings_worker_insert on app.knowledge_chunk_embeddings
for insert to app_rag_worker
with check ((select app_private.rag_worker_has_lease(generation_id, organization_id)));
create policy knowledge_chunk_embeddings_worker_delete on app.knowledge_chunk_embeddings
for delete to app_rag_worker
using ((select app_private.rag_worker_has_lease(generation_id, organization_id)));
