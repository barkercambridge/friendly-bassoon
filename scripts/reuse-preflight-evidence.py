#!/usr/bin/env python3
"""Fail-closed reuse of the successful push preflight for this exact release commit."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ARTIFACT = "virtual-admin-preflight-evidence"
WORKFLOW = "preflight.yml"
WAIT_SECONDS = 600
POLL_SECONDS = 15

def gh(*args):
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode:
        raise RuntimeError("GitHub CLI failed: " + " ".join(args) + ": " + proc.stderr[-1500:])
    return proc.stdout

def select_run(runs, sha):
    matches = [run for run in runs if run.get("head_sha") == sha
               and run.get("event") == "push" and run.get("head_branch") == "main"]
    return max(matches, key=lambda run: run.get("id", 0), default=None)

def main():
    sha = os.environ["RELEASE_SHA"]
    repo = os.environ["GH_REPO"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid release commit SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid GitHub repository")
    deadline = time.monotonic() + WAIT_SECONDS
    run = None
    while True:
        response = json.loads(gh("api", f"repos/{repo}/actions/workflows/{WORKFLOW}/runs",
                                 "-f", "event=push", "-f", "head_sha=" + sha,
                                 "-f", "per_page=100", "--method", "GET"))
        run = select_run(response.get("workflow_runs", []), sha)
        if run and run.get("status") == "completed":
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("No completed push preflight for this exact commit within 10 minutes")
        print("Waiting for main-push preflight for " + sha[:12], flush=True)
        time.sleep(POLL_SECONDS)
    if run.get("conclusion") != "success":
        raise RuntimeError("Preflight did not pass: " + str(run.get("html_url")))
    run_id = str(run["id"])
    print("Reusing successful push preflight: " + str(run.get("html_url")))
    gh("run", "download", run_id, "--repo", repo, "--name", ARTIFACT, "--dir", "release-evidence")
    for filename in ("powershell-syntax.json", "regression-results.json", "preflight-results.json"):
        path = Path("release-evidence") / filename
        if not path.is_file():
            raise RuntimeError("Missing preflight artifact: " + filename)
        evidence = json.loads(path.read_text(encoding="utf-8-sig"))
        if evidence.get("source_commit") != sha:
            raise RuntimeError("Preflight artifact source commit mismatch: " + filename)
    print("PASS: reusable preflight evidence belongs to release commit " + sha)

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        sys.exit(1)
