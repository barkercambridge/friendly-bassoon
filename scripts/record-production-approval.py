#!/usr/bin/env python3
"""Record automated production approval only after a passing current Devstan production gate."""
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
def fail(message):
    raise SystemExit("Production approval blocked: " + message)
def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))
def governing_devstan_version():
    text = (ROOT / "docs/development-standards.md").read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^\| \d{4}-\d{2}-\d{2} \| v(\d+\.\d+) \|", text)
    if not match:
        raise ValueError("Governing Devstan version missing")
    return match.group(1)

def required_acceptance_ids():
    inventory = json.loads((ROOT / "config/traceability.json").read_text(encoding="utf-8-sig"))
    entries = [x["id"] for x in inventory["acceptance_tests"]
               if x.get("stage") == "Acceptance" and x.get("status") == "required"]
    if not entries or len(entries) != len(set(entries)):
        raise ValueError("Invalid authoritative Acceptance inventory")
    return set(entries)

def main():
    report = read("release-evidence/devstan.json")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if report.get("source_commit") != sha or report.get("standard_version") != governing_devstan_version():
        fail("Devstan report source or version mismatch")
    checks = report.get("checks", [])
    if len(checks) != 8 or {x.get("rule") for x in checks} != {f"R{i:02d}" for i in range(1, 9)}:
        fail("incomplete Devstan verification")
    if not report.get("production_ready") or report.get("failed") or report.get("not_verified"):
        fail("mandatory controls have not all passed")
    if any(x.get("status") != "PASS" for x in checks):
        fail("mandatory controls not all PASS")
    if any(not isinstance(x.get("evidence"), str) or not x["evidence"].strip() or
           not isinstance(x.get("detail"), str) or not x["detail"].strip() for x in checks):
        fail("mandatory rule evidence references or verification details missing")
    if any(not x.get("verification_method") or not x.get("timestamp_utc") or
           not isinstance(x.get("applicable_checks"), list) or not x["applicable_checks"] or
           not isinstance(x.get("prerequisites"), list) for x in checks):
        fail("mandatory rule verification attribution incomplete")
    equivalence = read("release-evidence/source-equivalence.json")
    tested = equivalence.get("tested_commit")
    if not re.fullmatch(r"[0-9a-f]{40}", tested or "") or equivalence.get("release_commit") != sha or not equivalence.get("equivalent") or equivalence.get("release_affecting_changes"):
        fail("source equivalence not established")
    version = report["version"]
    paths = [ROOT / "tests/results/acceptance-results.json"] if (ROOT / "tests/results/acceptance-results.json").is_file() else []
    required = required_acceptance_ids()
    match = None
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        tests = data.get("tests", [])
        if (data.get("version") == version and data.get("source_commit") == tested and
            data.get("passed") == len(required) and data.get("failed") == 0 and data.get("blocked") == 0 and
            len(tests) == len(required) and {x.get("test_id") for x in tests} == required and
            all(x.get("status") == "PASS" for x in tests)):
            match = (path,)
            break
        if data.get("version") == version:
            fail("latest acceptance run for this version is not fully passing")
    if not match:
        fail("matching original acceptance evidence missing")
    manifest = read("release-evidence/evidence-manifest.json")
    if (manifest.get("source_commit") != sha or manifest.get("version") != version or
        manifest.get("edition") != "production" or not manifest.get("devstan_production_ready")):
        fail("evidence manifest source/version/edition mismatch")
    file_entries = manifest.get("files", [])
    paths_in_manifest = [entry.get("path") for entry in file_entries]
    if len(paths_in_manifest) != len(set(paths_in_manifest)):
        fail("duplicate evidence manifest paths")
    required_manifest = {"release-evidence/devstan.json",
                         "info/test-results.pdf", "info/test-evidence.pdf", "info/traceability.xlsx",
                         "tests/results/acceptance-results.json",
                         "tests/results/code-coverage.json", "info/test-coverage.pdf",
                         "release-evidence/source-equivalence.json",
                         "dist/virtual-admin-production-v" + version + ".zip"}
    if not required_manifest.issubset(set(paths_in_manifest)):
        fail("missing mandatory evidence manifest entries")
    required_reports = {"info/traceability.xlsx", "info/test-results.pdf", "info/test-evidence.pdf", "info/test-coverage.pdf"}
    if not required_reports.issubset(set(paths_in_manifest)):
        fail("pre-approval report checksums missing")
    for entry in file_entries:
        path = entry.get("path", "")
        if (not isinstance(path, str) or pathlib.PurePosixPath(path).is_absolute() or
            ".." in pathlib.PurePosixPath(path).parts):
            fail("invalid manifest path")
        file = ROOT / path
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != entry.get("sha256"):
            fail("evidence manifest checksum mismatch: " + path)
    result = {
        "application": "virtual-admin", "version": version,
        "method": "Automated verification", "approval_status": "APPROVED",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tested_commit": tested, "release_commit": sha,
        "acceptance_evidence": [str(p.relative_to(ROOT)).replace("\\", "/") for p in match],
        "devstan_evidence": "release-evidence/devstan.json",
        "evidence_manifest": "release-evidence/evidence-manifest.json",
        "source_equivalence_evidence": "release-evidence/source-equivalence.json",
        "production_package": "dist/virtual-admin-production-v" + version + ".zip",
        "mandatory_rules": {x["rule"]: x["status"] for x in checks},
        "mandatory_rule_evidence": {x["rule"]: {"status": x["status"], "evidence": x.get("evidence"), "detail": x.get("detail"), "verification_method": x.get("verification_method"), "timestamp_utc": x.get("timestamp_utc"), "applicable_checks": x.get("applicable_checks"), "prerequisites": x.get("prerequisites")} for x in checks},
    }
    dest = ROOT / "release-evidence/production-approval.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    manifest["files"].append({"path": "release-evidence/production-approval.json", "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "role": "production-approval"})
    (ROOT / "release-evidence/evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Automated production approval recorded and included in final manifest:", dest)
if __name__ == "__main__":
    main()
