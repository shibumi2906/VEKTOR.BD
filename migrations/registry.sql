CREATE SCHEMA registry;
-- next statement
CREATE TABLE registry.source_registry (
 source_id text PRIMARY KEY,
 source_type text NOT NULL CHECK (source_type IN ('official','manual','reference')),
 source_name text NOT NULL,
 check_interval_seconds integer NOT NULL CHECK (check_interval_seconds > 0),
 metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.document_families (
 family_id uuid PRIMARY KEY,
 slug text NOT NULL UNIQUE,
 title text NOT NULL,
 current_document_id uuid,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.document_versions (
 document_id uuid PRIMARY KEY,
 family_id uuid NOT NULL REFERENCES registry.document_families,
 title text NOT NULL, title_he text NOT NULL, title_ru text,
 document_type text NOT NULL, category text NOT NULL,
 language text NOT NULL CHECK (language = 'he'),
 version_label text,
 document_role text NOT NULL CHECK (document_role IN
 ('official','draft_contract','signed_contract','contract','template','reference')),
 version_status text NOT NULL CHECK (version_status IN
 ('current','superseded','historical','unknown')),
 legal_status text NOT NULL CHECK (legal_status IN
 ('in_force','repealed','not_yet_effective','unknown','not_applicable')),
 verification_status text NOT NULL CHECK (verification_status IN
 ('pending','verified','stale','failed','manual_review')),
 ingestion_status text NOT NULL DEFAULT 'registered' CHECK (ingestion_status IN
 ('registered','parsing','parsed','indexing','ready','failed')),
 publication_date date, effective_from date, effective_to date,
 source_id text NOT NULL REFERENCES registry.source_registry,
 source_url text NOT NULL, source_name text NOT NULL, issuer text NOT NULL,
 raw_file_key text NOT NULL,
 file_sha256 text NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
 size_bytes bigint NOT NULL CHECK (size_bytes > 0),
 page_count integer NOT NULL CHECK (page_count > 0),
 checked_at timestamptz, indexed_at timestamptz,
 metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(family_id,file_sha256), UNIQUE(family_id,document_id),
 CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from),
 CHECK (document_role <> 'template' OR legal_status = 'not_applicable')
);
-- next statement
ALTER TABLE registry.document_families ADD CONSTRAINT current_same_family
 FOREIGN KEY (family_id,current_document_id)
 REFERENCES registry.document_versions(family_id,document_id);
-- next statement
CREATE INDEX documents_source ON registry.document_versions(source_id);
-- next statement
CREATE FUNCTION registry.preserve_original() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.document_id,NEW.family_id,NEW.file_sha256,NEW.raw_file_key) IS DISTINCT FROM
    (OLD.document_id,OLD.family_id,OLD.file_sha256,OLD.raw_file_key) THEN
   RAISE EXCEPTION 'Document original identity is immutable';
 END IF;
 RETURN NEW;
END $$;
-- next statement
CREATE TRIGGER immutable_original BEFORE UPDATE ON registry.document_versions
 FOR EACH ROW EXECUTE FUNCTION registry.preserve_original();
-- next statement
CREATE TABLE registry.document_topics (
 document_id uuid NOT NULL REFERENCES registry.document_versions,
 topic text NOT NULL, title_he text NOT NULL,
 PRIMARY KEY(document_id,topic)
);
-- next statement
CREATE TABLE registry.source_checks (
 check_id uuid PRIMARY KEY,
 download_id text NOT NULL,
 source_id text NOT NULL REFERENCES registry.source_registry,
 document_id uuid REFERENCES registry.document_versions,
 source_url text NOT NULL,
 download_status text NOT NULL CHECK(download_status IN ('downloaded','failed')),
 checked_at timestamptz NOT NULL,
 metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.coverage_gaps (
 gap_id uuid PRIMARY KEY, metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.audit_events (
 event_id uuid PRIMARY KEY, document_id uuid REFERENCES registry.document_versions,
 event_type text NOT NULL, details jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE VIEW registry.document_register AS
 SELECT d.document_id, f.slug AS document_alias, d.title, d.document_type,
 d.category,d.language,d.version_label,d.document_role,d.source_name,d.issuer,
 d.source_url,d.publication_date,d.effective_from,d.effective_to,
 d.version_status,d.legal_status,d.verification_status,d.ingestion_status,
 d.file_sha256,d.page_count,d.checked_at,d.indexed_at,
 COALESCE((d.document_role='official' AND d.version_status='current'
 AND d.legal_status='in_force' AND d.verification_status='verified'
 AND d.effective_from <= (now() AT TIME ZONE 'Asia/Jerusalem')::date
 AND (d.effective_to IS NULL OR d.effective_to >
 (now() AT TIME ZONE 'Asia/Jerusalem')::date)),false) AS current_norms_eligible
 FROM registry.document_versions d JOIN registry.document_families f USING(family_id);
