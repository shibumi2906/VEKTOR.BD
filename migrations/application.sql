CREATE TABLE registry.projects (
 project_id uuid PRIMARY KEY, slug text NOT NULL UNIQUE, title text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.actors (
 actor_id uuid PRIMARY KEY, role text NOT NULL CHECK(role IN ('admin','reader')),
 token_hash text NOT NULL UNIQUE, enabled boolean NOT NULL DEFAULT true
);
-- next statement
CREATE TABLE registry.project_grants (
 actor_id uuid NOT NULL REFERENCES registry.actors,
 project_id uuid NOT NULL REFERENCES registry.projects,
 PRIMARY KEY(actor_id,project_id)
);
-- next statement
ALTER TABLE registry.document_families ADD COLUMN project_id uuid REFERENCES registry.projects;
-- next statement
ALTER TABLE registry.parsing_revisions ADD CONSTRAINT parsing_document_identity
 UNIQUE(document_id,parsing_revision);
-- next statement
CREATE TABLE registry.index_generations (
 generation_id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES registry.document_versions,
 parsing_revision uuid NOT NULL, fingerprint text NOT NULL, collection_name text NOT NULL,
 status text NOT NULL CHECK(status IN ('staging','ready','active','retired','failed')),
 expected_count integer NOT NULL CHECK(expected_count>0), verified_count integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(document_id,parsing_revision)
 REFERENCES registry.parsing_revisions(document_id,parsing_revision),
 UNIQUE(document_id,generation_id)
);
-- next statement
CREATE UNIQUE INDEX one_active_generation ON registry.index_generations(document_id)
 WHERE status='active';
-- next statement
ALTER TABLE registry.document_versions ADD COLUMN active_index_generation_id uuid;
-- next statement
ALTER TABLE registry.document_versions ADD CONSTRAINT generation_same_document
 FOREIGN KEY(document_id,active_index_generation_id)
 REFERENCES registry.index_generations(document_id,generation_id);
-- next statement
CREATE TABLE registry.generation_chunks (
 generation_id uuid NOT NULL REFERENCES registry.index_generations,
 chunk_id uuid NOT NULL REFERENCES registry.chunks,
 point_id uuid NOT NULL UNIQUE,
 PRIMARY KEY(generation_id,chunk_id)
);
-- next statement
CREATE TABLE registry.lexical_vocabulary (
 token text PRIMARY KEY, dimension integer NOT NULL UNIQUE CHECK(dimension>=0)
);
-- next statement
CREATE TABLE registry.jobs (
 job_id uuid PRIMARY KEY, actor_id uuid REFERENCES registry.actors,
 document_id uuid REFERENCES registry.document_versions,
 type text NOT NULL CHECK(type IN ('ingest','index','reindex','source_check')),
 status text NOT NULL CHECK(status IN ('pending','running','completed','failed','cancelled')),
 stage text NOT NULL DEFAULT 'pending', progress double precision NOT NULL DEFAULT 0
 CHECK(progress>=0 AND progress<=1), attempt integer NOT NULL DEFAULT 0,
 lease_until timestamptz, heartbeat_at timestamptz, retry_at timestamptz,
 cancel_requested boolean NOT NULL DEFAULT false,
 payload jsonb NOT NULL, result jsonb, error_code text,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.job_checkpoints (
 job_id uuid NOT NULL REFERENCES registry.jobs, stage text NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(job_id,stage)
);
-- next statement
CREATE TABLE registry.idempotency_records (
 actor_id uuid NOT NULL REFERENCES registry.actors, route text NOT NULL, key text NOT NULL,
 request_hash text NOT NULL, response jsonb NOT NULL,
 PRIMARY KEY(actor_id,route,key)
);
-- next statement
CREATE TABLE registry.provider_usage (
 usage_id uuid PRIMARY KEY, request_id uuid NOT NULL, model text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.comparison_reports (
 report_id uuid PRIMARY KEY, actor_id uuid NOT NULL REFERENCES registry.actors,
 document_a uuid NOT NULL REFERENCES registry.document_versions,
 document_b uuid NOT NULL REFERENCES registry.document_versions,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
