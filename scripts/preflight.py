#!/usr/bin/env python3
# FR-013: Validate Windows acceptance and regression prerequisites.
"""Read-only, fail-closed validation before release preparation."""
import pathlib
import datetime as dt
import json
import re
import py_compile
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

def main():
    import yaml
    errors = []
    workflows = sorted((ROOT / ".github/workflows").glob("*.yml"))
    if not workflows:
        errors.append("No GitHub Actions workflows found")
    for path in workflows:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            if not isinstance(document, dict) or "jobs" not in document:
                raise ValueError("Missing jobs mapping")
            if "on" not in document and True not in document:
                raise ValueError("Missing workflow triggers")
            print("PASS workflow:", path.relative_to(ROOT))
        except (yaml.YAMLError, ValueError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts:
            continue
        try:
            py_compile.compile(str(path), cfile=str(path.parent / "__pycache__" / (path.stem + ".preflight.pyc")), doraise=True)
        except (SyntaxError, OSError, py_compile.PyCompileError) as exc:
            errors.append(f"Python syntax {path.relative_to(ROOT)}: {exc}")
    # R04: reject executable references to the obsolete repository-root traceability file.
    obsolete = re.compile(r'(?:ROOT|root|Path\(__file__\)\.resolve\(\)\.parent(?:\.parent)?|Path\(["\x27]\.["\x27]\))\s*/\s*["\x27]traceability\.json["\x27]|Path\(["\x27]traceability\.json["\x27]\)')
    for source in sorted((ROOT / "scripts").glob("*.py")):
        if obsolete.search(source.read_text(encoding="utf-8-sig")):
            errors.append(f"Obsolete traceability path in {source.relative_to(ROOT)}")
    # Verify release version consumers use the authoritative source, including Git history lookups.
    for relative in ("scripts/build-formatting-checks.py", "scripts/build-test-reports.py",
                     "scripts/verify-final-evidence-manifest.py", "scripts/build-release-notes.py"):
        source = (ROOT / relative).read_text(encoding="utf-8-sig")
        if "config/traceability.json" not in source:
            errors.append(f"Application version source not authoritative: {relative}")
    if not (ROOT / "config/traceability.json").is_file():
        errors.append("Authoritative application version file missing")
    rtm = json.loads((ROOT / "config/traceability.json").read_text(encoding="utf-8-sig"))
    # R04: independently validate all three classified roles before regression execution.
    roles = ("implementation_source", "test_implementation", "coverage_instrumentation")
    global_roles = {}
    for requirement in rtm["requirements"]:
        planned = requirement.get("status") == "planned"
        if not all(isinstance(requirement.get(role), list) for role in roles):
            errors.append(f"{requirement['id']}: missing R04 traceability classifications")
            continue
        paths = [p for role in roles for p in requirement[role]]
        if len(paths) != len(set(paths)) or any(not isinstance(p, str) or not p or not (ROOT / p).is_file() for p in paths):
            errors.append(f"{requirement['id']}: invalid or overlapping R04 paths")
        for role in roles:
            for path in requirement[role]:
                if path in global_roles and global_roles[path] != role:
                    errors.append(f"{path}: prohibited multi-role file ({global_roles[path]}, {role})")
                global_roles[path] = role
        if planned and paths:
            errors.append(f"{requirement['id']}: planned requirement has implementation mappings")
        if not planned and (not requirement["implementation_source"] or not requirement["test_implementation"]):
            errors.append(f"{requirement['id']}: missing implementation or test classification")
    valid_fr = {r["id"] for r in rtm["requirements"]}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit")
    suites = rtm.get('regression_suites', [])
    if (not suites or len({row['id'] for row in suites}) != len(suites) or
        any(not re.fullmatch(r'RT-\d{3}', row['id']) for row in suites) or
        len({row['file'] for row in suites}) != len(suites) or
        any(not (ROOT / row['file']).is_file() or not row['file'].startswith('tests/') or
            not row['requirements'] or len(row['requirements']) != len(set(row['requirements'])) or
            not set(row['requirements']).issubset(valid_fr) for row in suites)):
        raise ValueError('Invalid authoritative regression suite mappings')
    implementation = subprocess.run(
        [sys.executable, "scripts/verify-acceptance-implementation.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if implementation.returncode:
        errors.append("Required Acceptance implementation coverage: " + (implementation.stdout + implementation.stderr)[-3000:])
    records = []
    for row in suites:
        test_id, test, requirements = row['id'], row['file'], row['requirements']
        if not set(requirements).issubset(valid_fr):
            raise ValueError("Regression mapping references unknown FR")
        try:
            result = subprocess.run([sys.executable, test], cwd=ROOT, capture_output=True, text=True, timeout=180)
            status = "PASS" if result.returncode == 0 else "FAIL"
            detail = (result.stdout + "\n" + result.stderr)[-12000:]
        except subprocess.TimeoutExpired:
            status, detail = "BLOCKED", "Regression suite timed out"
        records.append({"test_id": test_id, "file": test, "requirements": requirements, "status": status,
                        "detail": detail, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
        print(f"{status} regression: {test_id} {test}")
        if status != "PASS":
            errors.append(f"{test_id}: {detail[-3000:]}")
    report = {"schema_version": 1, "application": "virtual-admin", "version": rtm["version"],
              "source_commit": commit, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "tests": records}
    evidence_path = ROOT / "release-evidence/regression-results.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/verify-documentation-evidence.py", "--acceptance-build"],
        cwd=ROOT, capture_output=True, text=True,
    )
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'} evidence alignment")
    if result.returncode:
        errors.append("Evidence alignment: " + (result.stdout + result.stderr)[-3000:])
    results_dir = ROOT / "tests/results"
    if results_dir.exists():
        if not results_dir.is_dir():
            errors.append("Acceptance results path must be a directory")
        else:
            entries = list(results_dir.iterdir())
            if any(not p.is_file() or p.name not in ("acceptance-results.json", "code-coverage.json", "coverage-diagnostics.json") for p in entries):
                errors.append("Historical or unexpected acceptance evidence found")
            elif any(p.name == "acceptance-results.json" for p in entries):
                try:
                    data = json.loads((results_dir / "acceptance-results.json").read_text(encoding="utf-8-sig"))
                    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
                        errors.append("Invalid acceptance JSON schema")
                except (ValueError, OSError):
                    errors.append("Unreadable acceptance JSON")
    diagnostics_path = results_dir / "coverage-diagnostics.json"
    if diagnostics_path.is_file():
        try:
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8-sig"))
            coverage = json.loads((results_dir / "code-coverage.json").read_text(encoding="utf-8-sig"))
            if (not isinstance(diagnostics, dict) or not isinstance(diagnostics.get("files"), list)
                    or not diagnostics.get("source_commit")
                    or diagnostics["source_commit"] != coverage.get("source_commit")):
                errors.append("Coverage diagnostics schema or source association invalid")
        except (OSError, ValueError, AttributeError):
            errors.append("Coverage diagnostics or authoritative coverage unreadable")
    for message in errors:
        print("FAIL:", message, file=sys.stderr)
    print(f"Preflight: {'FAIL' if errors else 'PASS'} ({len(errors)} issues)")
    return int(bool(errors))

if __name__ == "__main__":
    sys.exit(main())
