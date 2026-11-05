#!/usr/bin/env python3
"""Verify final production evidence manifest after automated approval (Devstan R06–R08)."""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIRED = {
    "release-evidence/devstan.json", "release-evidence/source-equivalence.json",
    "release-evidence/production-approval.json",
    "tests/results/acceptance-results.json", "tests/results/code-coverage.json",
    "info/traceability.xlsx", "info/test-results.pdf", "info/test-evidence.pdf",
    "info/test-coverage.pdf",
}

def verify(root=ROOT):
    errors = []
    manifest = json.loads((root / "release-evidence/evidence-manifest.json").read_text(encoding="utf-8-sig"))
    approval = json.loads((root / "release-evidence/production-approval.json").read_text(encoding="utf-8-sig"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    version = json.loads((root / "traceability.json").read_text(encoding="utf-8-sig"))["version"]
    if manifest.get("edition") != "production" or manifest.get("source_commit") != head or manifest.get("version") != version or manifest.get("devstan_production_ready") is not True:
        errors.append("Manifest provenance or production gate invalid")
    if approval.get("approval_status") != "APPROVED" or approval.get("release_commit") != head or approval.get("version") != version:
        errors.append("Production approval invalid")
    rule_evidence = approval.get("mandatory_rule_evidence")
    required_rules = {f"R{i:02d}" for i in range(1, 9)}
    if (not isinstance(rule_evidence, dict) or set(rule_evidence) != required_rules or
        any(not isinstance(record, dict) or record.get("status") != "PASS" or
            not isinstance(record.get("evidence"), str) or not record["evidence"].strip() or
            not isinstance(record.get("detail"), str) or not record["detail"].strip() or
            not record.get("verification_method") or not record.get("timestamp_utc") or
            not isinstance(record.get("applicable_checks"), list) or not record["applicable_checks"] or
            not isinstance(record.get("prerequisites"), list)
            for record in rule_evidence.values())):
        errors.append("Production approval lacks complete attributable Devstan rule evidence")
    entries = manifest.get("files", [])
    if not isinstance(entries, list):
        return ["Manifest files must be a list"]
    paths = [x.get("path") for x in entries if isinstance(x, dict)]
    if len(paths) != len(entries) or len(set(paths)) != len(paths):
        errors.append("Missing, invalid or duplicate manifest entries")
    expected = REQUIRED | {"dist/virtual-admin-production-v" + version + ".zip"}
    if not expected.issubset(set(x for x in paths if isinstance(x, str))):
        errors.append("Required production evidence absent from manifest")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path or pathlib.PurePosixPath(path).is_absolute() or ".." in pathlib.PurePosixPath(path).parts:
            errors.append("Invalid manifest path")
            continue
        file = root / path
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != entry.get("sha256"):
            errors.append("Missing file or SHA-256 mismatch: " + path)
    return errors

if __name__ == "__main__":
    problems = verify()
    for problem in problems:
        print("FAIL:", problem)
    print("Final production manifest:", "FAIL" if problems else "PASS")
    sys.exit(bool(problems))
