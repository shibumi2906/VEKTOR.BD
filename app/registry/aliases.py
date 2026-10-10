import unicodedata


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def resolve(rows, reference, project_id=None):
    needle = normalized(reference)
    if not needle:
        return []
    candidates = [
        r
        for r in rows
        if (project_id is None or r["project_id"] == project_id)
        and needle
        in {normalized(r[k]) for k in ("document_alias", "title", "title_he", "version_label")}
    ]
    if len(candidates) > 1:
        current = [
            r
            for r in candidates
            if r["version_status"] == "current" and r["verification_status"] == "verified"
        ]
        if len(current) == 1 and len({r["family_id"] for r in candidates}) == 1:
            return current
    return candidates
