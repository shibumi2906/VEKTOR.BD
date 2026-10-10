from datetime import UTC, datetime

from app.registry.legal_engine import text_hash

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
OLD = "התקופה היא שלושים ימים."
NEW = "התקופה היא שישים ימים."


def evidence(clause="1"):
    return {
        "title": "מסמך בדיקה סינתטי",
        "issuer": "מחבר בדיקה סינתטי",
        "url": "https://example.invalid/synthetic-law.pdf",
        "file_sha256": "a" * 64,
        "publication_date": "2025-01-01",
        "page": 1,
        "clause": clause,
    }


def chain_data():
    return {
        "law_slug": "synthetic_rule",
        "title_he": "כלל סינתטי",
        "baseline_effective_from": "2025-01-01",
        "baseline_verification_status": "verified",
        "clauses": [{"clause_id": "1", "text_he": OLD, "source": evidence()}],
        "amendments": [
            {
                "amendment_id": "change_1",
                "sequence": 1,
                "effective_from": "2026-01-01",
                "verification_status": "verified",
                "changes": [
                    {
                        "operation": "replace",
                        "clause_id": "1",
                        "expected_text_sha256": text_hash(OLD),
                        "new_text_he": NEW,
                    }
                ],
                "source": evidence("2"),
            }
        ],
        "review": {
            "verification_status": "verified",
            "complete": True,
            "covered_from": "2025-01-01",
            "checked_through": "2026-10-09",
            "checked_at": "2026-10-09T10:00:00Z",
            "next_check_at": "2026-10-10T10:00:00Z",
            "reviewed_by": "synthetic_reviewer",
            "inventory_source": evidence("inventory"),
            "expected_amendment_ids": ["change_1"],
        },
    }
