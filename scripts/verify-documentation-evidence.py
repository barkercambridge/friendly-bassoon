#!/usr/bin/env python3
"""Fail-closed specification/evidence consistency check for Devstan R04/R07."""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIRED = {f"AT-{i:03d}" for i in range(1, 9)} | {"AT-010", "AT-011"}
SHA = re.compile(r"^[0-9a-f]{40}$")

def verify(root, production=False, acceptance_build=False):
    issues = []
    def issue(message):
        issues.append(message)
    def load(path):
        try:
            return json.loads((root / path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            issue(f"Missing/invalid JSON {path}: {exc}")
            return None

    spec_path = root / "docs/functional-specification.md"
    try:
        spec = spec_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return [f"Cannot read functional specification: {exc}"]
    # Validate the governing source reference without duplicating its version.
    standard_ref = re.search(r"(?m)^\*\*Governing development standard:\*\* \x60([^\x60]+)\x60\s*$", spec)
    if not standard_ref or standard_ref.group(1) != "docs/development-standards.md":
        issue("Specification governing Devstan source reference missing or invalid")
    elif not (root / standard_ref.group(1)).is_file():
        issue("Specification governing Devstan document missing")
    if not re.search(r"(?m)^\*\*Application version:\*\* \x60config/traceability.json\x60\s*$", spec):
        issue("Specification authoritative application version reference missing")
    if not re.search(r"(?m)^\*\*Document version:\*\* See Section 10, Change history\s*$", spec):
        issue("Specification document version history reference missing")
    rtm = load("config/traceability.json")
    if not isinstance(rtm, dict):
        return issues
    version = rtm.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        issue("Invalid MAJOR.MINOR application release version in config/traceability.json")
    fr_spec = {}
    for match in re.finditer(r"(?m)^- \*\*(FR-\d{3}) \[([^]]+)\]\*\*", spec):
        if match.group(1) in fr_spec:
            issue("Duplicate specification requirement " + match.group(1))
        fr_spec[match.group(1)] = match.group(2)
    fr_rtm = {r["id"]: r for r in rtm.get("requirements", []) if isinstance(r, dict) and "id" in r}
    if set(fr_spec) != set(fr_rtm) or len(fr_rtm) != len(rtm.get("requirements", [])):
        issue("FR identifiers do not match config/traceability.json")
    for fr, row in fr_rtm.items():
        if fr in fr_spec and (("planned" in fr_spec[fr].lower()) !=
                             (row.get("status", "").lower() == "planned")):
            issue(f"{fr} planned/implemented status mismatch")

    spec_matrix = {}
    section = spec.split("## 5. Acceptance test matrix", 1)
    if len(section) != 2:
        issue("Acceptance test matrix section missing")
    else:
        for line in section[1].split("\n## ", 1)[0].splitlines():
            cells = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(cells) >= 4 and re.fullmatch(r"AT-\d{3}", cells[0]):
                if cells[0] in spec_matrix:
                    issue("Duplicate specification matrix test " + cells[0])
                spec_matrix[cells[0]] = set(re.findall(r"FR-\d{3}", cells[1]))
                if re.match(r"^(PASS|FAIL|BLOCKED|NOT VERIFIED)\b", cells[3]):
                    issue("Test result stored in functional specification: " + cells[0])
    if not REQUIRED.issubset(spec_matrix):
        issue("Specification acceptance matrix omits mandatory tests")
    pending_tests = set(re.findall(r"(?m)^\|\s*(AT-\d{3})\s*\[Pending\]", spec))
    if set(spec_matrix) - REQUIRED != pending_tests:
        issue("Additional acceptance matrix tests must be explicitly marked Pending")
    for fr, row in fr_rtm.items():
        for at in row.get("tests", []):
            if at not in spec_matrix or fr not in spec_matrix[at]:
                issue(f"{fr} to {at} traceability differs from specification matrix")
    for at, frs in spec_matrix.items():
        for fr in frs:
            if at not in fr_rtm.get(fr, {}).get("tests", []):
                issue(f"Matrix {at} to {fr} absent from config/traceability.json")

    reports = [root / "tests/results/acceptance-results.json"] if (root / "tests/results/acceptance-results.json").is_file() else []
    if (root / "tests/results").exists() and any(p.name not in ("acceptance-results.json", "code-coverage.json") for p in (root / "tests/results").iterdir()):
        issue("Unexpected historical or additional acceptance evidence")
    current = []
    for path in reports:
        data = load(str(path.relative_to(root)))
        if isinstance(data, dict) and data.get("version") == version:
            current.append((path, data))
    if not current:
        if production or not acceptance_build:
            issue("No acceptance JSON evidence for current version")
    else:
        path, data = current[0]
        commit = data.get("source_commit")
        if not isinstance(commit, str) or not SHA.fullmatch(commit):
            issue("Acceptance source commit missing or invalid")
        tests = data.get("tests", [])
        if not isinstance(tests, list) or any(not isinstance(t, dict) for t in tests):
            issue("Acceptance tests must be a list of records")
            tests = []
        ids = [t.get("test_id") for t in tests]
        if set(ids) != REQUIRED or len(ids) != len(REQUIRED):
            issue("Acceptance evidence has missing, extra or duplicate AT IDs")
        for test in tests:
            at = test.get("test_id")
            if at in spec_matrix and set(test.get("requirements", [])) != spec_matrix[at]:
                issue(f"Acceptance JSON {at} requirements differ from specification")
            if test.get("status") not in ("PASS", "FAIL", "BLOCKED"):
                issue(f"Acceptance JSON {at} has invalid status")
        counts = {status: sum(t.get("status") == status for t in tests)
                  for status in ("PASS", "FAIL", "BLOCKED")}
        if any(data.get(key) != counts[status] for key, status in
               (("passed", "PASS"), ("failed", "FAIL"), ("blocked", "BLOCKED"))):
            issue("Acceptance JSON totals do not match individual test statuses")
        if production and counts != {"PASS": len(REQUIRED), "FAIL": 0, "BLOCKED": 0}:
            issue("Production requires all mandatory acceptance tests PASS")


    coverage_path = root / "tests/results/code-coverage.json"
    if production and not coverage_path.is_file():
        issue("Production requires machine-readable code coverage evidence")
    if coverage_path.is_file():
        coverage = load("tests/results/code-coverage.json")
        if isinstance(coverage, dict):
            if production and (not current or not re.fullmatch(r"[0-9a-f]{64}", current[0][1].get("acceptance_zip_sha256", "") or "") or coverage.get("acceptance_zip_sha256") != current[0][1].get("acceptance_zip_sha256")):
                issue("Acceptance ZIP SHA-256 missing or inconsistent between acceptance and coverage evidence")
            if coverage.get("version") != version:
                issue("Code coverage version mismatch")
            if not current or coverage.get("source_commit") != current[0][1].get("source_commit"):
                issue("Code coverage tested commit differs from acceptance evidence")
            files = coverage.get("files")
            if not isinstance(files, list) or not files:
                issue("Code coverage file inventory missing")
            elif production:
                for required_path in ("src/compare-formatting.ps1", "src/archive-previous-outputs.ps1"):
                    matching = [x for x in files if isinstance(x, dict) and x.get("path") == required_path]
                    if len(matching) != 1 or matching[0].get("measurement") != "MEASURED" or not matching[0].get("covered_lines"):
                        issue("Required execution coverage not measured: " + required_path)


    approval_path = root / "release-evidence/production-approval.json"
    if approval_path.is_file():
        approval = load("release-evidence/production-approval.json")
        if isinstance(approval, dict) and approval.get("approval_status") == "APPROVED":
            if not current or approval.get("tested_commit") != current[0][1].get("source_commit"):
                issue("Approval JSON tested commit differs from acceptance evidence")
            if approval.get("version") != version:
                issue("Approval JSON version differs from specification")
            if "Automated verification" not in spec:
                issue("Specification omits automated approval method")
    return issues

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--acceptance-build", action="store_true", help="Allow missing current-version Word acceptance evidence only while building an unapproved acceptance ZIP")
    args = parser.parse_args()
    issues = verify(args.root, args.production, args.acceptance_build)
    for message in issues:
        print("FAIL:", message)
    print("Documentation/evidence alignment:", "FAIL" if issues else "PASS")
    return int(bool(issues))

if __name__ == "__main__":
    sys.exit(main())
