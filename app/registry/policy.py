"""Corpus selection policy; historical amendments are never current consolidated laws."""

EXCLUDED_KINDS = frozenset(
    {
        "amendment_gazette",
        "gazette_erratum",
        "base_law",
        "base_law_with_amendments",
        "temporary_law",
        "enacted_law",
        "consolidated_snapshot",
    }
)


def validate_current_policy(corpus):
    if corpus.get("retention_policy") != "current_only":
        return
    for row in corpus["documents"]:
        if row["artifact_kind"] in EXCLUDED_KINDS:
            raise ValueError("Current-only corpus rejects historical law publications/amendments")
        if row["artifact_kind"] == "consolidated_law" and not (
            row.get("version_status") == "current"
            and row.get("legal_status") == "in_force"
            and row.get("verification_status") == "verified"
            and row.get("consolidation_verified_as_of")
        ):
            raise ValueError("A consolidated law requires explicit current-edition verification")
