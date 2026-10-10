CREATE TABLE registry.legal_laws (
 law_id uuid PRIMARY KEY,
 slug text NOT NULL UNIQUE,
 title_he text NOT NULL,
 current_chain_id uuid,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE TABLE registry.legal_chains (
 chain_id uuid PRIMARY KEY,
 law_id uuid NOT NULL REFERENCES registry.legal_laws,
 input_sha256 text NOT NULL CHECK(input_sha256 ~ '^[0-9a-f]{64}$'),
 verification_status text NOT NULL CHECK(verification_status IN
 ('verified','pending','manual_review','failed')),
 covered_from date NOT NULL,
 checked_through date NOT NULL,
 checked_at timestamptz NOT NULL,
 next_check_at timestamptz NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(law_id,input_sha256), UNIQUE(law_id,chain_id),
 CHECK(covered_from <= checked_through), CHECK(checked_at < next_check_at)
);
-- next statement
ALTER TABLE registry.legal_laws ADD CONSTRAINT current_chain_same_law
 FOREIGN KEY(law_id,current_chain_id) REFERENCES registry.legal_chains(law_id,chain_id);
-- next statement
CREATE TABLE registry.legal_amendments (
 chain_id uuid NOT NULL REFERENCES registry.legal_chains,
 amendment_id text NOT NULL,
 sequence integer NOT NULL CHECK(sequence >= 0),
 effective_from date, effective_to date,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(chain_id,amendment_id), UNIQUE(chain_id,sequence),
 CHECK(effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from)
);
-- next statement
CREATE TABLE registry.legal_snapshots (
 snapshot_sha256 text PRIMARY KEY CHECK(snapshot_sha256 ~ '^[0-9a-f]{64}$'),
 chain_id uuid NOT NULL REFERENCES registry.legal_chains,
 as_of date NOT NULL,
 facts_sha256 text NOT NULL CHECK(facts_sha256 ~ '^[0-9a-f]{64}$'),
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- next statement
CREATE FUNCTION registry.preserve_legal_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Legal evidence/snapshots are immutable; register a new reviewed chain';
END $$;
-- next statement
CREATE TRIGGER immutable_legal_chain BEFORE UPDATE ON registry.legal_chains
 FOR EACH ROW EXECUTE FUNCTION registry.preserve_legal_evidence();
-- next statement
CREATE TRIGGER immutable_legal_amendment BEFORE UPDATE ON registry.legal_amendments
 FOR EACH ROW EXECUTE FUNCTION registry.preserve_legal_evidence();
-- next statement
CREATE TRIGGER immutable_legal_snapshot BEFORE UPDATE ON registry.legal_snapshots
 FOR EACH ROW EXECUTE FUNCTION registry.preserve_legal_evidence();
