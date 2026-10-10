CREATE TABLE registry.parsing_revisions (
 parsing_revision uuid PRIMARY KEY,
 document_id uuid NOT NULL REFERENCES registry.document_versions,
 parser_fingerprint text NOT NULL CHECK (parser_fingerprint ~ '^[0-9a-f]{64}$'),
 quality jsonb NOT NULL,
 manifest_key text NOT NULL,
 artifact_sha256 text NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(document_id,parser_fingerprint)
);
-- next statement
CREATE TABLE registry.blocks (
 parsing_revision uuid NOT NULL REFERENCES registry.parsing_revisions,
 block_id uuid NOT NULL,
 ordinal integer NOT NULL CHECK (ordinal >= 0),
 original_text text NOT NULL,
 search_text text NOT NULL,
 normalization_map jsonb NOT NULL,
 locator jsonb NOT NULL,
 structure jsonb NOT NULL,
 PRIMARY KEY(parsing_revision,block_id), UNIQUE(parsing_revision,ordinal)
);
-- next statement
CREATE TABLE registry.chunks (
 chunk_id uuid PRIMARY KEY,
 parsing_revision uuid NOT NULL REFERENCES registry.parsing_revisions,
 chunking_fingerprint text NOT NULL CHECK (chunking_fingerprint ~ '^[0-9a-f]{64}$'),
 text text NOT NULL,
 content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
 spans jsonb NOT NULL,
 metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TRIGGER immutable_parsing BEFORE UPDATE ON registry.parsing_revisions
 FOR EACH ROW EXECUTE FUNCTION registry.preserve_legal_evidence();
-- next statement
CREATE TRIGGER immutable_block BEFORE UPDATE ON registry.blocks
 FOR EACH ROW EXECUTE FUNCTION registry.preserve_legal_evidence();
-- next statement
CREATE TRIGGER immutable_chunk BEFORE UPDATE ON registry.chunks
 FOR EACH ROW EXECUTE FUNCTION registry.preserve_legal_evidence();
