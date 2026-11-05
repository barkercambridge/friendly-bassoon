#!/usr/bin/env python3
"""Record per-check preflight evidence for the current commit."""
import datetime as dt
import json
import pathlib
import subprocess
import sys
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

def main():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    checks = []
    def add(name, passed, evidence):
        checks.append(dict(name=name, status="PASS" if passed else "FAIL", evidence=evidence))
    regression = json.loads((ROOT / "release-evidence/regression-results.json").read_text(encoding="utf-8-sig"))
    syntax = json.loads((ROOT / "release-evidence/powershell-syntax.json").read_text(encoding="utf-8-sig"))
    add("regression", regression.get("source_commit") == sha and len(regression.get("tests", [])) == len(json.loads((ROOT / "traceability.json").read_text(encoding="utf-8-sig"))["regression_suites"]) and all(x.get("status") == "PASS" for x in regression["tests"]), "release-evidence/regression-results.json")
    add("powershell", syntax.get("source_commit") == sha and bool(syntax.get("scripts")) and all(x.get("result") == "PASS" and x.get("encoding_compatible") for x in syntax["scripts"]), "release-evidence/powershell-syntax.json")
    workflows = list((ROOT / ".github/workflows").glob("*.yml"))
    add("workflows", bool(workflows) and all(isinstance(yaml.safe_load(p.read_text(encoding="utf-8-sig")), dict) for p in workflows), ".github/workflows")
    add("python", all(compile(p.read_bytes(), str(p), "exec") is not None for p in ROOT.rglob("*.py") if ".git" not in p.parts), "repository Python files")
    result = dict(source_commit=sha, timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat(), checks=checks, status="PASS" if all(x["status"] == "PASS" for x in checks) else "FAIL")
    path = ROOT / "release-evidence/preflight-results.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
