#!/usr/bin/env python3
"""Verify acceptance evidence freshness; clean only the ephemeral preflight checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "tests/results"
POLICY_PATH = ROOT / "config/release-input-exemptions.json"

def exemptions():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    evidence = set(policy["evidence_paths"])
    editorial = set(policy["editorial_paths"])
    if evidence != {"tests/results/acceptance-results.json", "tests/results/code-coverage.json"}:
        raise ValueError("Unexpected authoritative evidence exemptions")
    if policy.get("evidence_directory") != "tests/results/":
        raise ValueError("Invalid generated-evidence directory exemption")
    if evidence & editorial or any(p.startswith("tests/results/") for p in editorial):
        raise ValueError("Invalid editorial exemptions")
    return evidence, editorial

EVIDENCE = {"acceptance-results.json", "code-coverage.json"}
SUPPORTING_DIAGNOSTICS = {"coverage-diagnostics.json"}

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.PIPE).strip()

def fingerprint(commit):
    evidence, editorial = exemptions()
    entries = []
    for line in git("ls-tree", "-r", "--full-tree", commit).splitlines():
        metadata, path = line.split("\t", 1)
        if path.startswith("tests/results/") or path in editorial:
            continue
        entries.append(path + "\t" + metadata)
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()

def freshness():
    if not RESULTS.exists():
        return "ABSENT", "No acceptance evidence"
    if not RESULTS.is_dir():
        return "INVALID", "Results path is not a directory"
    files = list(RESULTS.iterdir())
    if not files:
        return "ABSENT", "No acceptance evidence"
    if any(not p.is_file() or p.name not in (EVIDENCE | SUPPORTING_DIAGNOSTICS) for p in files):
        return "INVALID", "Unexpected results files"
    if not EVIDENCE.issubset({p.name for p in files}):
        return "INVALID", "Incomplete evidence pair"
    try:
        acceptance = json.loads((RESULTS / "acceptance-results.json").read_text(encoding="utf-8-sig"))
        coverage = json.loads((RESULTS / "code-coverage.json").read_text(encoding="utf-8-sig"))
        tested = acceptance["source_commit"]
        if not isinstance(tested, str) or not re.fullmatch("[0-9a-f]{40}", tested):
            return "INVALID", "Invalid tested commit"
        if coverage["source_commit"] != tested:
            return "INVALID", "Acceptance and coverage provenance differ"
        git("cat-file", "-e", tested + "^{commit}")
        current = git("rev-parse", "HEAD")
        git("merge-base", "--is-ancestor", tested, current)
        expected = fingerprint(tested)
        if acceptance.get("release_input_fingerprint") != expected or coverage.get("release_input_fingerprint") != expected:
            return "INVALID", "Evidence release-input fingerprint missing or inconsistent"
        actual = fingerprint(current)
        if expected != actual:
            return "STALE", "Release-input fingerprint differs"
        return "VALID", "Release-input fingerprint " + actual
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        return "INVALID", "Cannot verify provenance: " + str(exc)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean-stale-workspace", action="store_true")
    parser.add_argument("--print-fingerprint", metavar="COMMIT")
    args = parser.parse_args()
    if args.print_fingerprint:
        try:
            print(fingerprint(args.print_fingerprint))
            return 0
        except (OSError, ValueError, subprocess.CalledProcessError):
            return 1
    status, reason = freshness()
    print("Acceptance evidence:", status, "-", reason)
    if status in ("STALE", "INVALID") and args.clean_stale_workspace:
        if not RESULTS.is_dir():
            return 1
        for path in RESULTS.iterdir():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        print("Cleared stale evidence in CI workspace; repository unchanged")
        return 0
    return 0 if status in ("VALID", "ABSENT") else 1

if __name__ == "__main__":
    sys.exit(main())
