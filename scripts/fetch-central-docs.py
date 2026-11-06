#!/usr/bin/env python3
"""Materialize pinned private central standards into the ephemeral checkout.

No network access is attempted without STANDARDS_READ_TOKEN. Never log credentials.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
PIN = ROOT / "config/central-standards.json"
EXPECTED = {"docs/development-standards.md", "docs/python-defect-register.md", "docs/development-defect-register.md", "docs/development-standards-register.json"}

def fetch():
    config = json.loads(PIN.read_text(encoding="utf-8"))
    repo, commit = config["repository"], config["commit"]
    paths = set(config["documents"])
    if repo != "barkercambridge/miniature-memory" or not re.fullmatch(r"[a-f0-9]{40}", commit) or paths != EXPECTED:
        raise ValueError("Invalid pinned central standards configuration")
    token = os.environ.get("STANDARDS_READ_TOKEN", "")
    if not token:
        raise ValueError("STANDARDS_READ_TOKEN is required for private central standards")
    contents = {}
    for path in sorted(paths):
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={commit}"
        req = Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "virtual-admin-central-standards",
        })
        with urlopen(req, timeout=30) as response:
            obj = json.load(response)
        if obj.get("type") != "file" or obj.get("encoding") != "base64":
            raise ValueError("Unexpected central document response: " + path)
        raw = base64.b64decode(obj["content"], validate=False)
        blob_sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob_sha != obj.get("sha"):
            raise ValueError("Central document blob integrity mismatch: " + path)
        contents[path] = raw
    central = json.loads(contents["docs/development-standards-register.json"].decode("utf-8-sig"))
    registered = {x["path"] for x in central["documents"]}
    if not EXPECTED.issubset(registered):
        raise ValueError("Central document register missing required documents")
    # Write only after every download and integrity check succeeds.
    for path, raw in contents.items():
        dest = ROOT / path if path != "docs/development-standards-register.json" else ROOT / "external/miniature-memory/docs/development-standards-register.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    print(f"Central standards verified at {repo}@{commit}; {len(contents)} documents materialized")

if __name__ == "__main__":
    try:
        fetch()
    except (ValueError, KeyError, OSError, HTTPError, URLError) as exc:
        print("Central standards retrieval failed:", type(exc).__name__, file=sys.stderr)
        sys.exit(1)
