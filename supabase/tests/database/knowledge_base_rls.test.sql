begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to app_api;
grant execute on all functions in schema extensions to app_api;
set local search_path = public, extensions;

select plan(33);

select has_table('app', 'knowledge_sources', 'knowledge sources table exists');
select has_table(
  'app',
  'knowledge_source_versions',
  'knowledge source versions table exists'
);
select ok(
  (
    select bool_and(class.relrowsecurity and class.relforcerowsecurity)
    from pg_catalog.pg_class as class
    inner join pg_catalog.pg_namespace as namespace on namespace.oid = class.relnamespace
    where namespace.nspname = 'app'
      and class.relname in ('knowledge_sources', 'knowledge_source_versions')
  ),
  'all knowledge tables enable and force RLS'
);
select col_not_null(
  'app',
  'knowledge_sources',
  'organization_id',
  'knowledge sources require an organization'
);
select col_not_null(
  'app',
  'knowledge_source_versions',
  'organization_id',
  'knowledge versions require an organization'
);
select ok(
  pg_catalog.has_table_privilege('app_api', 'app.knowledge_sources', 'select'),
  'app_api may select source metadata'
);
select ok(
  not pg_catalog.has_table_privilege('app_api', 'app.knowledge_source_versions', 'select'),
  'app_api has no table-wide version select privilege'
);
select ok(
  pg_catalog.has_column_privilege(
    'app_api',
    'app.knowledge_source_versions',
    'normalized_text',
    'select'
  ),
  'app_api may select normalized knowledge content'
);
select ok(
  not pg_catalog.has_column_privilege(
    'app_api',
    'app.knowledge_source_versions',
    'storage_key',
    'select'
  ),
  'ordinary version reads cannot access storage keys'
);
select ok(
  pg_catalog.has_function_privilege(
    'app_api',
    'app_private.knowledge_file_objects(uuid,uuid)',
    'execute'
  ),
  'app_api may invoke the guarded file-object lookup'
);
select ok(
  not pg_catalog.has_schema_privilege('authenticated', 'app', 'usage'),
  'Supabase authenticated clients cannot access knowledge tables'
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
    '51000000-0000-0000-0000-000000000001',
    'knowledge-owner-a@example.test',
    '{}',
    '{}',
    now(),
    now()
  ),
  (
    '51000000-0000-0000-0000-000000000002',
    'knowledge-admin-a@example.test',
    '{}',
    '{}',
    now(),
    now()
  ),
  (
    '51000000-0000-0000-0000-000000000003',
    'knowledge-member-a@example.test',
    '{}',
    '{}',
    now(),
    now()
  ),
  (
    '51000000-0000-0000-0000-000000000004',
    'knowledge-owner-b@example.test',
    '{}',
    '{}',
    now(),
    now()
  ),
  (
    '51000000-0000-0000-0000-000000000005',
    'knowledge-outsider@example.test',
    '{}',
    '{}',
    now(),
    now()
  );

insert into app.organizations (id, name, created_by_user_id)
values
  (
    '52000000-0000-0000-0000-000000000001',
    'Knowledge Organization A',
    '51000000-0000-0000-0000-000000000001'
  ),
  (
    '52000000-0000-0000-0000-000000000002',
    'Knowledge Organization B',
    '51000000-0000-0000-0000-000000000004'
  ),
  (
    '52000000-0000-0000-0000-000000000003',
    'Knowledge cleanup organization',
    '51000000-0000-0000-0000-000000000001'
  );

insert into app.organization_memberships (id, organization_id, user_id, role)
values
  (
    '53000000-0000-0000-0000-000000000001',
    '52000000-0000-0000-0000-000000000001',
    '51000000-0000-0000-0000-000000000001',
    'owner'
  ),
  (
    '53000000-0000-0000-0000-000000000002',
    '52000000-0000-0000-0000-000000000001',
    '51000000-0000-0000-0000-000000000002',
    'admin'
  ),
  (
    '53000000-0000-0000-0000-000000000003',
    '52000000-0000-0000-0000-000000000001',
    '51000000-0000-0000-0000-000000000003',
    'member'
  ),
  (
    '53000000-0000-0000-0000-000000000004',
    '52000000-0000-0000-0000-000000000002',
    '51000000-0000-0000-0000-000000000004',
    'owner'
  );

insert into app.knowledge_sources (
  id,
  organization_id,
  kind,
  title,
  created_by_user_id,
  updated_by_user_id
)
values
  (
    '54000000-0000-0000-0000-000000000001',
    '52000000-0000-0000-0000-000000000001',
    'article',
    'Organization A article',
    '51000000-0000-0000-0000-000000000001',
    '51000000-0000-0000-0000-000000000001'
  ),
  (
    '54000000-0000-0000-0000-000000000002',
    '52000000-0000-0000-0000-000000000001',
    'document',
    'Organization A document',
    '51000000-0000-0000-0000-000000000001',
    '51000000-0000-0000-0000-000000000001'
  ),
  (
    '54000000-0000-0000-0000-000000000003',
    '52000000-0000-0000-0000-000000000002',
    'article',
    'Organization B article',
    '51000000-0000-0000-0000-000000000004',
    '51000000-0000-0000-0000-000000000004'
  ),
  (
    '54000000-0000-0000-0000-000000000004',
    '52000000-0000-0000-0000-000000000001',
    'article',
    'Cascade test article',
    '51000000-0000-0000-0000-000000000001',
    '51000000-0000-0000-0000-000000000001'
  ),
  (
    '54000000-0000-0000-0000-000000000005',
    '52000000-0000-0000-0000-000000000003',
    'article',
    'Organization cleanup guard',
    '51000000-0000-0000-0000-000000000001',
    '51000000-0000-0000-0000-000000000001'
  );

insert into app.knowledge_source_versions (
  id,
  organization_id,
  source_id,
  kind,
  version_number,
  status,
  raw_text,
  normalized_text,
  locator_map,
  original_filename,
  media_type,
  size_bytes,
  sha256,
  storage_key,
  extractor_name,
  extractor_version,
  processing_attempts,
  processing_started_at,
  processed_at,
  created_by_user_id
)
values
  (
    '55000000-0000-0000-0000-000000000001',
    '52000000-0000-0000-0000-000000000001',
    '54000000-0000-0000-0000-000000000001',
    'article',
    1,
    'ready',
    'Article content',
    'Article content',
    '{"schema_version":1,"segments":[{"kind":"text","start":0,"end":15}]}',
    null,
    null,
    null,
    null,
    null,
    'manual',
    '1',
    0,
    null,
    now(),
    '51000000-0000-0000-0000-000000000001'
  ),
  (
    '55000000-0000-0000-0000-000000000002',
    '52000000-0000-0000-0000-000000000001',
    '54000000-0000-0000-0000-000000000002',
    'document',
    1,
    'ready',
    null,
    'Document content',
    '{"schema_version":1,"segments":[{"kind":"page","page":1,"start":0,"end":16}]}',
    'handbook.pdf',
    'application/pdf',
    100,
    repeat('a', 64),
    '52000000-0000-0000-0000-000000000001/54000000-0000-0000-0000-000000000002/55000000-0000-0000-0000-000000000002/content',
    'pypdf',
    '1',
    1,
    now(),
    now(),
    '51000000-0000-0000-0000-000000000001'
  ),
  (
    '55000000-0000-0000-0000-000000000003',
    '52000000-0000-0000-0000-000000000002',
    '54000000-0000-0000-0000-000000000003',
    'article',
    1,
    'ready',
    'Foreign article',
    'Foreign article',
    '{"schema_version":1,"segments":[{"kind":"text","start":0,"end":15}]}',
    null,
    null,
    null,
    null,
    null,
    'manual',
    '1',
    0,
    null,
    now(),
    '51000000-0000-0000-0000-000000000004'
  ),
  (
    '55000000-0000-0000-0000-000000000004',
    '52000000-0000-0000-0000-000000000001',
    '54000000-0000-0000-0000-000000000004',
    'article',
    1,
    'ready',
    'Cascade content',
    'Cascade content',
    '{"schema_version":1,"segments":[{"kind":"text","start":0,"end":15}]}',
    null,
    null,
    null,
    null,
    null,
    'manual',
    '1',
    0,
    null,
    now(),
    '51000000-0000-0000-0000-000000000001'
  );

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000003","role":"authenticated"}',
  true
);
select is(
  (select count(*) from app.knowledge_sources),
  3::bigint,
  'a member sees source metadata only in their organization'
);
select is(
  (
    select normalized_text
    from app.knowledge_source_versions
    where id = '55000000-0000-0000-0000-000000000001'
  ),
  'Article content',
  'a member may read normalized knowledge content'
);
select throws_ok(
  $$
    select storage_key
    from app.knowledge_source_versions
    where id = '55000000-0000-0000-0000-000000000002'
  $$,
  '42501',
  'permission denied for table knowledge_source_versions',
  'a member cannot read storage keys through the version table'
);
select is(
  (
    select count(*)
    from app_private.knowledge_file_objects(
      '52000000-0000-0000-0000-000000000001',
      '54000000-0000-0000-0000-000000000002'
    )
  ),
  0::bigint,
  'a member cannot resolve an original file for download'
);
select throws_ok(
  $$
    insert into app.knowledge_sources (
      organization_id,
      kind,
      title,
      created_by_user_id,
      updated_by_user_id
    )
    values (
      '52000000-0000-0000-0000-000000000001',
      'article',
      'Forbidden member article',
      '51000000-0000-0000-0000-000000000003',
      '51000000-0000-0000-0000-000000000003'
    )
  $$,
  '42501',
  'new row violates row-level security policy for table "knowledge_sources"',
  'a member cannot create knowledge'
);
update app.knowledge_sources
set title = 'Forbidden member update',
    updated_by_user_id = '51000000-0000-0000-0000-000000000003'
where id = '54000000-0000-0000-0000-000000000001';
reset role;
select is(
  (
    select title
    from app.knowledge_sources
    where id = '54000000-0000-0000-0000-000000000001'
  ),
  'Organization A article',
  'a member cannot update source metadata'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000003","role":"authenticated"}',
  true
);
delete from app.knowledge_sources
where id = '54000000-0000-0000-0000-000000000001';
reset role;
select is(
  (
    select count(*)
    from app.knowledge_sources
    where id = '54000000-0000-0000-0000-000000000001'
  ),
  1::bigint,
  'a member cannot delete a source'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000002","role":"authenticated"}',
  true
);
select is(
  (
    select storage_key
    from app_private.knowledge_file_objects(
      '52000000-0000-0000-0000-000000000001',
      '54000000-0000-0000-0000-000000000002'
    )
    where version_id = '55000000-0000-0000-0000-000000000002'
  ),
  '52000000-0000-0000-0000-000000000001/54000000-0000-0000-0000-000000000002/55000000-0000-0000-0000-000000000002/content',
  'an admin may resolve an original file for download'
);
reset role;

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
select is(
  (
    select original_filename
    from app_private.knowledge_file_objects(
      '52000000-0000-0000-0000-000000000001',
      '54000000-0000-0000-0000-000000000002'
    )
    where version_id = '55000000-0000-0000-0000-000000000002'
  ),
  'handbook.pdf',
  'an owner may resolve an original file for download'
);
select is(
  (select count(*) from app.knowledge_sources),
  3::bigint,
  'an owner cannot read another organization source'
);
update app.knowledge_sources
set title = 'Updated article',
    updated_by_user_id = '51000000-0000-0000-0000-000000000001'
where id = '54000000-0000-0000-0000-000000000001';
reset role;
select is(
  (
    select title
    from app.knowledge_sources
    where id = '54000000-0000-0000-0000-000000000001'
  ),
  'Updated article',
  'an owner may update source metadata'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
select throws_ok(
  $$
    update app.knowledge_source_versions
    set normalized_text = 'Mutated ready content'
    where id = '55000000-0000-0000-0000-000000000001'
  $$,
  '23514',
  'ready knowledge source versions are immutable',
  'ready source content is immutable'
);
reset role;

select throws_ok(
  $$
    insert into app.knowledge_source_versions (
      id,
      organization_id,
      source_id,
      kind,
      version_number,
      status,
      raw_text,
      normalized_text,
      locator_map,
      extractor_name,
      extractor_version,
      processed_at,
      created_by_user_id
    )
    values (
      '55000000-0000-0000-0000-000000000005',
      '52000000-0000-0000-0000-000000000001',
      '54000000-0000-0000-0000-000000000003',
      'article',
      2,
      'ready',
      'Forged content',
      'Forged content',
      '{"schema_version":1,"segments":[]}',
      'manual',
      '1',
      now(),
      '51000000-0000-0000-0000-000000000001'
    )
  $$,
  '23503',
  'insert or update on table "knowledge_source_versions" violates foreign key constraint "knowledge_source_versions_source_fk"',
  'tenant-aware foreign keys reject a cross-organization version'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000005","role":"authenticated"}',
  true
);
select is(
  (select count(*) from app.knowledge_sources),
  0::bigint,
  'an outsider cannot read any knowledge source'
);
select is(
  (select count(*) from app.knowledge_source_versions),
  0::bigint,
  'an outsider cannot read normalized knowledge versions'
);
select is(
  (
    select count(*)
    from app_private.knowledge_file_objects(
      '52000000-0000-0000-0000-000000000001',
      '54000000-0000-0000-0000-000000000002'
    )
  ),
  0::bigint,
  'an outsider cannot resolve original files'
);
reset role;

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000004","role":"authenticated"}',
  true
);
update app.knowledge_sources
set title = 'Cross-tenant update',
    updated_by_user_id = '51000000-0000-0000-0000-000000000004'
where id = '54000000-0000-0000-0000-000000000001';
reset role;
select is(
  (
    select title
    from app.knowledge_sources
    where id = '54000000-0000-0000-0000-000000000001'
  ),
  'Updated article',
  'an owner cannot update another organization source'
);

select throws_ok(
  $$
    delete from app.organizations
    where id = '52000000-0000-0000-0000-000000000003'
  $$,
  '23503',
  'update or delete on table "organizations" violates foreign key constraint "knowledge_sources_organization_id_fkey" on table "knowledge_sources"',
  'organization deletion is restricted until stored knowledge is cleaned up'
);

set local role app_api;
select set_config(
  'request.jwt.claims',
  '{"sub":"51000000-0000-0000-0000-000000000001","role":"authenticated"}',
  true
);
delete from app.knowledge_sources
where id = '54000000-0000-0000-0000-000000000004';
reset role;
select is(
  (
    select count(*)
    from app.knowledge_source_versions
    where source_id = '54000000-0000-0000-0000-000000000004'
  ),
  0::bigint,
  'source deletion cascades to immutable versions'
);

select has_index(
  'app',
  'knowledge_source_versions',
  'knowledge_source_versions_current_unique_idx',
  'current knowledge versions have a unique partial index'
);
select has_index(
  'app',
  'knowledge_sources',
  'knowledge_sources_organization_created_idx',
  'organization source listing is indexed'
);
select ok(
  not pg_catalog.has_table_privilege('api_login', 'app.knowledge_sources', 'select'),
  'the login role has no direct knowledge privileges'
);

select * from finish();
rollback;
