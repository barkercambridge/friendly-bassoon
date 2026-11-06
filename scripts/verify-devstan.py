#!/usr/bin/env python3
"""Evidence-based Devstan assessment. Does not execute Word acceptance tests."""
import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import re
import sys
import subprocess
import zipfile
import hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANDATORY = [f"AT-{i:03d}" for i in range(1, 9)] + ["AT-010", "AT-011"]

def governing_devstan_version():
    text = (ROOT / "docs/development-standards.md").read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^\| \d{4}-\d{2}-\d{2} \| v(\d+\.\d+) \|", text)
    if not match:
        raise ValueError("Governing Devstan version missing")
    return match.group(1)

def git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None

def check(production=False):
    rtm = json.loads((ROOT / "config/traceability.json").read_text(encoding="utf-8-sig"))
    spec = (ROOT / "docs/functional-specification.md").read_text(encoding="utf-8-sig")
    checks = []
    def add(rule, passed, evidence, detail, pending=False):
        checks.append(dict(rule=f"R{rule:02d}", status="NOT VERIFIED" if pending else ("PASS" if passed else "FAIL"),
                           evidence=evidence, detail=detail,
                           verification_method="Automated evidence verification",
                           timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                           prerequisites=[]))
    ids = [r.get("id") for r in rtm["requirements"]]
    fr_ok = bool(ids) and len(ids) == len(set(ids)) and all(re.fullmatch(r"FR-\d{3}", x or "") and x in spec for x in ids)
    # R02 is a composite gate: FR checks plus current preflight and register evidence.
    head = git_sha()
    preflight_path = ROOT / "release-evidence/regression-results.json"
    syntax_path = ROOT / "release-evidence/powershell-syntax.json"
    preflight_ok = False
    try:
        regression = json.loads(preflight_path.read_text(encoding="utf-8-sig"))
        syntax = json.loads(syntax_path.read_text(encoding="utf-8-sig"))
        preflight_ok = (regression.get("source_commit") == head and
                        syntax.get("source_commit") == head and
                        bool(regression.get("tests")) and
                        all(t.get("status") == "PASS" for t in regression["tests"]) and
                        bool(syntax.get("scripts")) and
                        all(s.get("result") == "PASS" and s.get("encoding_compatible")
                            for s in syntax["scripts"]))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    # Validate controlled document and workflow inventories before claiming R02 PASS.
    document_ok = False
    workflow_ok = False
    try:
        import importlib.machinery
        loader = importlib.machinery.SourceFileLoader("document_register_verifier", str(ROOT / "scripts/verify-document-register.py"))
        module = loader.load_module()
        document_ok = not module.validate(ROOT)
        workflows = list((ROOT / ".github/workflows").glob("*.yml"))
        workflow_ok = bool(workflows) and all("jobs:" in path.read_text(encoding="utf-8-sig") and "on:" in path.read_text(encoding="utf-8-sig") for path in workflows)
    except (ImportError, OSError, ValueError, TypeError, KeyError):
        pass
    preflight_ok = preflight_ok and document_ok and workflow_ok
    try:
        summary = json.loads((ROOT / "release-evidence/preflight-results.json").read_text(encoding="utf-8-sig"))
        preflight_ok = preflight_ok and summary.get("source_commit") == head and summary.get("status") == "PASS" and len(summary.get("checks", [])) >= 4 and all(x.get("status") == "PASS" and x.get("evidence") for x in summary["checks"])
    except (OSError, ValueError, TypeError, KeyError):
        preflight_ok = False
    add(2, fr_ok and preflight_ok, "config/traceability.json;docs/functional-specification.md;"
        "release-evidence/regression-results.json;release-evidence/powershell-syntax.json",
        "FR identifiers and current preflight regression/syntax evidence verified" if fr_ok and preflight_ok
        else "FR or current preflight evidence incomplete",
        pending=not production and not preflight_ok)
    mappings = []
    for r in rtm["requirements"]:
        planned = r.get("status", "").lower() == "planned"
        sources, tests = r.get("source", []), r.get("tests", [])
        mappings.append(planned or (bool(sources) and bool(tests) and all((ROOT / p).is_file() for p in sources)
                                     and all(t in MANDATORY for t in tests)))
    # FR-linked comments are mandatory in mapped executable source, not data files.
    # Match actual comment lines rather than FR identifiers in strings or code.
    comment_prefixes = {".ps1": "#", ".py": "#", ".bat": "rem", ".cmd": "rem"}
    missing_comments = []
    for requirement in rtm["requirements"]:
        if requirement.get("status", "").lower() == "planned":
            continue
        fr_id = requirement["id"]
        for source in requirement.get("source", []):
            path = ROOT / source
            prefix = comment_prefixes.get(path.suffix.lower())
            if prefix is None or not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeError):
                missing_comments.append(f"{fr_id}: unreadable {source}")
                continue
            if prefix == "#":
                found = any(re.match(r"^\s*#(?!!)", line) and re.search(r"(?<![A-Za-z0-9-])" + re.escape(fr_id) + r"(?![0-9])", line) for line in lines)
            else:
                found = any(re.match(r"^\s*(?:rem\b|::)", line, re.IGNORECASE) and re.search(r"(?<![A-Za-z0-9-])" + re.escape(fr_id) + r"(?![0-9])", line) for line in lines)
            if not found:
                missing_comments.append(f"{fr_id}: {source}")
    coverage_ok = False
    if production:
        try:
            coverage = json.loads((ROOT / "tests/results/code-coverage.json").read_text(encoding="utf-8-sig"))
            acceptance = json.loads((ROOT / "tests/results/acceptance-results.json").read_text(encoding="utf-8-sig"))
            files = coverage.get("files", [])
            measured = {row.get("path") for row in files if isinstance(row, dict)
                        and row.get("measurement") == "MEASURED" and row.get("covered_lines")}
            coverage_ok = (coverage.get("version") == rtm["version"] and
                           coverage.get("source_commit") == acceptance.get("source_commit") and
                           isinstance(files, list) and bool(files) and
                           {"src/compare-formatting.ps1", "src/archive-previous-outputs.ps1"}.issubset(measured) and
                           all(isinstance(row, dict) and row.get("path") and
                               row.get("measurement") in ("MEASURED", "NOT MEASURED", "EXCLUDED")
                               for row in files))
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    if production and coverage_ok:
        try:
            expected_paths = {"src/compare-formatting.ps1", "src/archive-previous-outputs.ps1", "run-virtual-admin.bat"}
            paths = [row["path"] for row in files]
            coverage_ok = len(paths) == len(set(paths)) and expected_paths.issubset(set(paths))
            for row in files:
                executable = row.get("executable_lines", [])
                covered = row.get("covered_lines", [])
                uncovered = row.get("uncovered_lines", [])
                if not all(isinstance(a, list) and all(isinstance(n, int) and n > 0 for n in a) for a in (executable, covered, uncovered)):
                    coverage_ok = False
                    break
                if len(executable) != len(set(executable)) or set(covered) & set(uncovered) or set(covered) | set(uncovered) != set(executable):
                    coverage_ok = False
                    break
                if row["measurement"] == "MEASURED":
                    percentage = round(100 * len(covered) / len(executable), 2) if executable else None
                    if percentage is None or row.get("coverage_percentage") is None or abs(float(row["coverage_percentage"]) - percentage) > 0.011:
                        coverage_ok = False
                        break
                elif not row.get("reason") and not row.get("excluded"):
                    coverage_ok = False
                    break
                if row.get("excluded") and not row.get("reason"):
                    coverage_ok = False
                    break
            exclusions = coverage.get("exclusions", [])
            if not isinstance(exclusions, list) or {x.get("path") for x in exclusions} != {x.get("path") for x in files if x.get("excluded")}:
                coverage_ok = False
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            coverage_ok = False
    trace_ok = fr_ok and all(mappings) and not missing_comments and (coverage_ok if production else True)
    detail = ("Implemented FR source/AT mappings and FR-linked source comments" if trace_ok
              else "Missing mappings or FR comments: " + "; ".join(missing_comments or ["source/AT mapping invalid"]))
    add(4, trace_ok, "config/traceability.json;mapped source-code comments;tests/results/code-coverage.json",
        detail if trace_ok else detail + ("; code coverage missing or invalid" if production and not coverage_ok else ""))

    # Select the most recent complete original evidence, never a historical approval row.
    evidence_paths = []
    evidence_ok = False
    tested_commit = None
    candidates = [ROOT / "tests/results/acceptance-results.json"] if (ROOT / "tests/results/acceptance-results.json").is_file() else []
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if data.get("version") != rtm["version"]:
                continue
            tests = data.get("tests", [])
            commit = data.get("source_commit", "")
            valid = (bool(re.fullmatch(r"[0-9a-f]{40}", commit)) and
                     data.get("passed") == len(MANDATORY) and
                     data.get("failed") == 0 and data.get("blocked") == 0 and
                     len(tests) == len(MANDATORY) and
                     sorted(t.get("test_id") for t in tests) == sorted(MANDATORY) and
                     all(t.get("status") == "PASS" for t in tests))
            if valid:
                evidence_ok = True
                tested_commit = commit
                evidence_paths = [str(candidate.relative_to(ROOT)).replace("\\", "/")]
                break
            # A newer unsuccessful run for this version supersedes older PASS evidence.
            break
        except (OSError, ValueError, TypeError, KeyError):
            continue
    regression_ok = False
    try:
        reg = json.loads((ROOT / "release-evidence/regression-results.json").read_text(encoding="utf-8-sig"))
        suites = rtm.get("regression_suites", [])
        expected = {s["id"]: s for s in suites}
        rows = reg.get("tests", [])
        regression_ok = (bool(expected) and len(expected) == len(suites) and len(rows) == len(expected) and
                         reg.get("source_commit") == git_sha() and
                         {t.get("test_id") for t in rows} == set(expected) and
                         all(t.get("status") == "PASS" and
                             t.get("file") == expected[t["test_id"]]["file"] and
                             t.get("requirements") == expected[t["test_id"]]["requirements"]
                             for t in rows))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    acceptance_ok = evidence_ok
    evidence_ok = acceptance_ok and regression_ok
    add(3, evidence_ok, ";".join(evidence_paths) or "tests/results",
        "Original ten-test acceptance evidence and current regression suites checked; Word not executed by CI",
        pending=(not production and not evidence_ok))
    checks[-1]["applicable_checks"] = [{"name": "acceptance", "status": "PASS" if acceptance_ok else "NOT VERIFIED", "evidence": "tests/results/acceptance-results.json"}, {"name": "regression", "status": "PASS" if regression_ok else "FAIL", "evidence": "release-evidence/regression-results.json"}]

    # Objective checks are recorded as such; a presence check is not a runtime test.
    head = git_sha()
    equivalence_path = ROOT / "release-evidence/source-equivalence.json"
    equivalence = {}
    if equivalence_path.is_file():
        try:
            equivalence = json.loads(equivalence_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            pass
    equivalent = bool(evidence_ok and equivalence.get("equivalent") is True and
                      equivalence.get("tested_commit") == tested_commit and
                      equivalence.get("release_commit") == head and
                      not equivalence.get("release_affecting_changes"))
    add(1, equivalent if production else False, "release-evidence/source-equivalence.json",
        "No release-affecting differences from acceptance-tested source" if equivalent else
        "Scoped source-equivalence review required", pending=not production)

    syntax_path = ROOT / "release-evidence/powershell-syntax.json"
    syntax_ok = False
    if syntax_path.is_file():
        try:
            syntax = json.loads(syntax_path.read_text(encoding="utf-8-sig"))
            syntax_ok = (syntax.get("source_commit") == head and
                         bool(syntax.get("scripts")) and
                         all(s.get("result") == "PASS" and s.get("encoding_compatible")
                             for s in syntax["scripts"]))
        except (OSError, ValueError, TypeError):
            pass
    package_path = ROOT / ("dist/virtual-admin-production-v" + rtm["version"] + ".zip")
    package_ok = False
    if package_path.is_file():
        try:
            with zipfile.ZipFile(package_path) as z:
                names = set(z.namelist())
                required = {"run-virtual-admin.bat", "info/formatting-checks.pdf", "info/release.pdf", "info/test-results.pdf", "info/test-evidence.pdf", "info/test-coverage.pdf",
                            "src/compare-formatting.ps1", "config/format-checks.json",
                            "config/virtual-admin-build.json"}
                meta = json.loads(z.read("config/virtual-admin-build.json").decode("utf-8-sig"))
                package_ok = (required.issubset(names) and
                              not any(n.startswith("tests/") or n == "run-acceptance-tests.bat"
                                      for n in names) and
                              meta.get("source_commit") == head and
                              meta.get("version") == rtm["version"])
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            pass
    add(5, equivalent and package_ok, "release-evidence/source-equivalence.json;" +
        str(package_path.relative_to(ROOT)),
        "Source equivalence and production package provenance/layout verified" if
        equivalent and package_ok else "Source equivalence or production package not verified",
        pending=not production)

    # R08: verify edition-specific production deliverables before the approval gate.
    results_dir = ROOT / "tests/results"
    evidence_format_ok = not results_dir.exists() or (
        results_dir.is_dir() and all(p.is_file() and p.name in ("acceptance-results.json", "code-coverage.json")
                                     for p in results_dir.iterdir())
    )
    if production:
        required_reports = ("info/traceability.xlsx", "info/test-results.pdf",
                            "info/test-evidence.pdf", "info/test-coverage.pdf")
        reports_ok = all((ROOT / p).is_file() and (ROOT / p).stat().st_size > 0
                         for p in required_reports)
        if package_ok:
            try:
                with zipfile.ZipFile(package_path) as archive:
                    reports_ok = reports_ok and all(p in archive.namelist() for p in required_reports)
            except (OSError, zipfile.BadZipFile):
                reports_ok = False
        evidence_format_ok = evidence_format_ok and reports_ok and package_ok
    add(8, evidence_format_ok, "tests/results;info/traceability.xlsx;info/test-results.pdf;"
        "info/test-evidence.pdf;info/test-coverage.pdf;production ZIP",
        "Edition-specific reports and production package verified" if production and evidence_format_ok
        else "Acceptance JSON-only policy verified" if not production and evidence_format_ok
        else "Required edition-specific evidence or production reports not verified")

    # R06/R07 derive eligibility from all other mandatory controls, including R08.
    prereqs = [x for x in checks if x["rule"] not in ("R06", "R07")]
    gate_ready = all(x["status"] == "PASS" for x in prereqs)
    add(6, gate_ready, "release-evidence/production-approval.json",
        "Automated approval eligible only after all prerequisite controls PASS",
        pending=not production)
    add(7, gate_ready, "release-evidence/devstan.json",
        "Fail-closed gate: all prerequisites must PASS",
        pending=not production)
    for entry in checks:
        entry.setdefault("applicable_checks", [{"name": entry["rule"], "status": entry["status"], "evidence": entry["evidence"]}])
        if entry["rule"] in ("R06", "R07"):
            entry["prerequisites"] = [x["rule"] for x in prereqs]
    return rtm, checks

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="release-evidence/devstan.json")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    rtm, checks = check(args.production)
    report = dict(application="virtual-admin", standard_version=governing_devstan_version(), version=rtm["version"],
                  source_commit=git_sha(), timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  checks=sorted(checks, key=lambda x: x["rule"]),
                  passed=sum(c["status"] == "PASS" for c in checks),
                  failed=sum(c["status"] == "FAIL" for c in checks),
                  not_verified=sum(c["status"] == "NOT VERIFIED" for c in checks),
                  production_ready=all(c["status"] == "PASS" for c in checks))
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for item in report["checks"]:
        print(f"{item['rule']}: {item['status']} - {item['detail']}")
    print(f"Devstan: {report['passed']} PASS, {report['failed']} FAIL, {report['not_verified']} NOT VERIFIED. Production is blocked unless all mandatory controls pass.")
    return 1 if report["failed"] or (args.production and not report["production_ready"]) else 0

if __name__ == "__main__":
    raise SystemExit(main())
