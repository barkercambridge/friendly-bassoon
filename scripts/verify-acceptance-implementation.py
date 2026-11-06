#!/usr/bin/env python3
"""R03: fail closed when a required Acceptance test has no executable result path."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
RECORD = re.compile(r"(?m)^\s*Record\s+['\"](AT-\d{3})['\"]\s+['\"](PASS|FAIL|BLOCKED)['\"]")
# A static path check is necessary but not sufficient: actual execution is independently
# verified from the authoritative acceptance evidence by the production gate.
def verify(root=ROOT):
    inventory = json.loads((root / "config/traceability.json").read_text(encoding="utf-8-sig"))
    errors = []
    required = [row for row in inventory["acceptance_tests"] if row["status"] == "required" and row["stage"] == "Acceptance"]
    for row in required:
        path = root / row["implementation"]
        if not path.is_file():
            errors.append(f"{row['id']}: implementation file missing")
            continue
        source = path.read_text(encoding="utf-8-sig")
        # A generic missing-test BLOCKED fallback cannot establish executable coverage.
        explicit = {test for test, status in RECORD.findall(source) if status in ("PASS", "FAIL")}
        if row["id"] not in explicit:
            errors.append(f"{row['id']}: no executable PASS/FAIL recording path in {row['implementation']}")
    return errors

if __name__ == "__main__":
    issues = verify()
    for issue in issues:
        print("FAIL:", issue)
    raise SystemExit(bool(issues))
