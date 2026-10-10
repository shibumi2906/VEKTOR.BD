import hashlib

import pytest

from app.registry.policy import EXCLUDED_KINDS, validate_current_policy
from scripts.prune_corpus import checked_target


@pytest.mark.parametrize("kind", sorted(EXCLUDED_KINDS))
def test_current_policy_rejects_old_laws_and_amendments(kind):
    with pytest.raises(ValueError, match="rejects historical"):
        validate_current_policy(
            {"retention_policy": "current_only", "documents": [{"artifact_kind": kind}]}
        )


def test_current_law_requires_proof_not_just_title():
    row = {
        "artifact_kind": "consolidated_law",
        "version_status": "current",
        "legal_status": "in_force",
        "verification_status": "verified",
    }
    with pytest.raises(ValueError, match="explicit"):
        validate_current_policy({"retention_policy": "current_only", "documents": [row]})
    row["consolidation_verified_as_of"] = "2026-10-09"
    validate_current_policy({"retention_policy": "current_only", "documents": [row]})


def test_cleanup_never_targets_outside_raw_storage(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        checked_target(tmp_path / "contract.pdf", tmp_path / "data/raw", "0" * 64)


def test_cleanup_rejects_modified_file(tmp_path):
    file = tmp_path / "original.pdf"
    file.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        checked_target(file, tmp_path, hashlib.sha256(b"original").hexdigest())
    assert file.exists()
