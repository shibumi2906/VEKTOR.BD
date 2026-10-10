"""Validate stable requirement identities and plan coverage without external calls."""

import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
specification = (root / "docs/specification.md").read_text(encoding="utf-8")
traceability = (root / "docs/requirements-traceability.md").read_text(encoding="utf-8")
ids = re.findall(r"^(REQ-[A-Z]+-(?:\d+-)?\d+)\.", specification, re.M)
assert len(ids) == len(set(ids)), "Duplicate requirement IDs"
assert ids, "Requirements missing"
for identifier in ids:
    assert f"| {identifier} |" in traceability, f"Missing traceability: {identifier}"
sections = [int(item) for item in re.findall(r"^## (\d+) ", specification, re.M)]
assert sections == list(range(1, 59)), "Section numbering mismatch"
plan = (root / "docs/implementation-plan.md").read_text(encoding="utf-8")
tasks = re.findall(r"^## (T\d+) ", plan, re.M)
assert tasks == [f"T{index:02d}" for index in range(1, 15)]
assert not re.search(r"FullCompare|full_compare|/compare/full", specification)
print(f"Verified {len(ids)} unique requirements, traceability, 58 sections and 14 tasks")
