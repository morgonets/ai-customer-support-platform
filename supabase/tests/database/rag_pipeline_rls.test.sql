begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to app_api;
grant execute on all functions in schema extensions to app_api;
set local search_path = public, extensions;

select plan(24);

select has_table('app', 'rag_embedding_profiles', 'embedding profiles exist');
select has_table('app', 'organization_rag_settings', 'organization RAG settings exist');
select has_table('app', 'knowledge_chunk_sets', 'chunk sets exist');
select has_table('app', 'knowledge_chunks', 'chunks exist');
select has_table('app', 'knowledge_index_generations', 'index generations exist');
select has_table('app', 'knowledge_chunk_embeddings', 'chunk embeddings exist');
select ok(
  (
    select bool_and(class.relrowsecurity and class.relforcerowsecurity)
    from pg_catalog.pg_class as class
    inner join pg_catalog.pg_namespace as namespace on namespace.oid = class.relnamespace
    where namespace.nspname = 'app'
      and class.relname in (
        'organization_rag_settings', 'knowledge_chunk_sets', 'knowledge_chunks',
        'knowledge_index_generations', 'knowledge_chunk_embeddings'
      )
  ),
  'all tenant-owned RAG tables enable and force RLS'
);
select col_not_null(
  'app', 'knowledge_chunk_embeddings', 'organization_id',
  'chunk embeddings require an organization'
);
select col_type_is(
  'app', 'knowledge_chunk_embeddings', 'embedding', 'extensions.vector',
  'embeddings use variable-dimension pgvector storage'
);
select has_index(
  'app', 'knowledge_chunk_embeddings', 'knowledge_chunk_embeddings_hnsw_1536_idx',
  'the optional 1536-dimensional HNSW index exists'
);
select ok(
  not (select rolbypassrls from pg_catalog.pg_roles where rolname = 'app_rag_worker'),
  'the RAG worker cannot bypass RLS'
);
select ok(
  not pg_catalog.has_table_privilege(
    'service_role', 'app.knowledge_chunk_embeddings', 'select'
  ),
  'the Supabase service role cannot read embeddings'
);
select ok(
  not pg_catalog.has_column_privilege(
    'app_api', 'app.knowledge_index_generations', 'is_active', 'update'
  ),
  'the API role cannot activate generations directly'
);
select ok(
  not pg_catalog.has_column_privilege(
    'app_api', 'app.organization_rag_settings', 'active_profile_id', 'update'
  ),
  'the API role cannot switch the active embedding profile directly'
);
select ok(
  not pg_catalog.has_table_privilege(
    'app_rag_worker', 'app.knowledge_index_generations', 'update'
  ),
  'the worker can mutate lifecycle state only through guarded functions'
);
select ok(
  not pg_catalog.has_table_privilege('app_rag_worker', 'app.knowledge_chunks', 'delete'),
  'the worker cannot delete immutable chunks'
);
select ok(
  pg_catalog.has_function_privilege(
    'app_rag_worker', 'app_private.claim_rag_generation(text,integer)', 'execute'
  ),
  'the worker can claim durable jobs'
);
select ok(
  not pg_catalog.has_function_privilege(
    'app_api', 'app_private.complete_rag_generation(uuid,uuid,uuid,integer,integer)',
    'execute'
  ),
  'the request role cannot complete generations'
);
select extensions.is(
  (select dimensions from app.rag_embedding_profiles where profile_key = 'deterministic-local-v1'),
  1536,
  'the local reference profile uses 1536 dimensions'
);
select extensions.is(
  (select dimensions from app.rag_embedding_profiles
    where profile_key = 'openai-text-embedding-3-small-1536-v1'),
  1536,
  'the opt-in OpenAI profile uses 1536 dimensions'
);

insert into auth.users (
  id, email, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values
  ('71000000-0000-0000-0000-000000000001', 'rag-a@example.test', '{}', '{}', now(), now()),
  ('71000000-0000-0000-0000-000000000002', 'rag-b@example.test', '{}', '{}', now(), now());
insert into app.organizations (id, name, created_by_user_id) values
  ('72000000-0000-0000-0000-000000000001', 'RAG A', '71000000-0000-0000-0000-000000000001'),
  ('72000000-0000-0000-0000-000000000002', 'RAG B', '71000000-0000-0000-0000-000000000002');
insert into app.organization_memberships (id, organization_id, user_id, role) values
  ('73000000-0000-0000-0000-000000000001', '72000000-0000-0000-0000-000000000001',
   '71000000-0000-0000-0000-000000000001', 'owner'),
  ('73000000-0000-0000-0000-000000000002', '72000000-0000-0000-0000-000000000002',
   '71000000-0000-0000-0000-000000000002', 'owner');
insert into app.knowledge_sources (
  id, organization_id, kind, title, created_by_user_id, updated_by_user_id
) values
  ('74000000-0000-0000-0000-000000000001', '72000000-0000-0000-0000-000000000001',
   'article', 'RAG A article', '71000000-0000-0000-0000-000000000001',
   '71000000-0000-0000-0000-000000000001'),
  ('74000000-0000-0000-0000-000000000002', '72000000-0000-0000-0000-000000000002',
   'article', 'RAG B article', '71000000-0000-0000-0000-000000000002',
   '71000000-0000-0000-0000-000000000002');
insert into app.knowledge_source_versions (
  id, organization_id, source_id, kind, version_number, status, raw_text,
  normalized_text, locator_map, extractor_name, extractor_version, processed_at,
  created_by_user_id
) values
  ('75000000-0000-0000-0000-000000000001', '72000000-0000-0000-0000-000000000001',
   '74000000-0000-0000-0000-000000000001', 'article', 1, 'ready', 'A', 'A',
   '{"schema_version":1,"segments":[{"kind":"text","start":0,"end":1}]}',
   'manual', '1', now(), '71000000-0000-0000-0000-000000000001'),
  ('75000000-0000-0000-0000-000000000002', '72000000-0000-0000-0000-000000000002',
   '74000000-0000-0000-0000-000000000002', 'article', 1, 'ready', 'B', 'B',
   '{"schema_version":1,"segments":[{"kind":"text","start":0,"end":1}]}',
   'manual', '1', now(), '71000000-0000-0000-0000-000000000002');
insert into app.organization_rag_settings (
  organization_id, active_profile_id, updated_by_user_id
) values
  ('72000000-0000-0000-0000-000000000001', '70000000-0000-0000-0000-000000000001',
   '71000000-0000-0000-0000-000000000001'),
  ('72000000-0000-0000-0000-000000000002', '70000000-0000-0000-0000-000000000001',
   '71000000-0000-0000-0000-000000000002');
insert into app.knowledge_index_generations (
  id, organization_id, source_id, knowledge_source_version_id, embedding_profile_id,
  generation_number, requested_by_user_id
) values
  ('76000000-0000-0000-0000-000000000001', '72000000-0000-0000-0000-000000000001',
   '74000000-0000-0000-0000-000000000001', '75000000-0000-0000-0000-000000000001',
   '70000000-0000-0000-0000-000000000001', 1, '71000000-0000-0000-0000-000000000001'),
  ('76000000-0000-0000-0000-000000000002', '72000000-0000-0000-0000-000000000002',
   '74000000-0000-0000-0000-000000000002', '75000000-0000-0000-0000-000000000002',
   '70000000-0000-0000-0000-000000000001', 1, '71000000-0000-0000-0000-000000000002');

set local request.jwt.claims =
  '{"sub":"71000000-0000-0000-0000-000000000001","role":"authenticated"}';
set local role app_api;

select extensions.is(
  (select count(*) from app.organization_rag_settings), 1::bigint,
  'settings reads are tenant isolated'
);
select extensions.is(
  (select count(*) from app.knowledge_index_generations), 1::bigint,
  'generation reads are tenant isolated'
);
reset role;
delete from app.knowledge_sources
where id = '74000000-0000-0000-0000-000000000001';
select is(
  (select count(*) from app.knowledge_index_generations
   where source_id = '74000000-0000-0000-0000-000000000001'),
  0::bigint,
  'source deletion immediately removes all generation eligibility'
);
select is(
  (select count(*) from app.organization_rag_settings
   where organization_id = '72000000-0000-0000-0000-000000000001'),
  1::bigint,
  'source deletion retains organization-level RAG settings'
);

select * from finish();
rollback;
