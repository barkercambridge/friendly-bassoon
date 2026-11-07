#!/usr/bin/env python3
"""Verify controlled documents and generate run-specific Devstan/evidence records."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def validate(root, check_release_files=False):
    register = read_json(root / "docs/document-register.json")
    errors = []
    entries = register.get("documents", [])
    paths = [entry.get("path") for entry in entries]
    if len(paths) != len(set(paths)):
        errors.append("Duplicate document-register paths")
    if register.get("application") != "virtual-admin":
        errors.append("Invalid document-register application")
    allowed = {"required", "pattern", "generated", "conditional"}
    for entry in entries:
        path = entry.get("path")
        if not isinstance(path, str) or not path or pathlib.PurePosixPath(path).is_absolute() or ".." in pathlib.PurePosixPath(path).parts:
            errors.append("Invalid document path: " + repr(path))
            continue
        if not entry.get("authority") or entry.get("verification") not in allowed:
            errors.append("Incomplete register entry: " + path)
        if entry.get("generator") and entry.get("verification") != "generated":
            errors.append("Generator declared for non-generated file: " + path)
        if entry.get("verification") == "generated":
            generator = entry.get("generator")
            if not isinstance(generator, str) or not generator or not (root / generator).is_file():
                errors.append("Missing generated-file producer: " + path)
            if "release_required" in entry and not isinstance(entry["release_required"], bool):
                errors.append("Invalid release_required value: " + path)
        elif "release_required" in entry and not isinstance(entry["release_required"], bool):
            errors.append("Invalid release_required value: " + path)
        if entry.get("verification") == "required" and (check_release_files or not path.startswith("info/")) and not (root / path).is_file():
            errors.append("Missing required document: " + path)
        if entry.get("verification") == "pattern" and not list(root.glob(path)):
            errors.append("Missing required evidence pattern: " + path)
    # Validate source authority against the DevStan policy table, not an independently inferred mapping.
    authority_entries = register.get("authoritative_sources")
    if not isinstance(authority_entries, list):
        errors.append("Missing authoritative source mappings")
        authority_entries = []
    assignments = {}
    for item in authority_entries:
        if not isinstance(item, dict):
            errors.append("Invalid authoritative source assignment")
            continue
        kind, path = item.get("information_type"), item.get("path")
        if not isinstance(kind, str) or not kind or kind in assignments:
            errors.append("Duplicate or invalid authoritative information type: " + repr(kind))
            continue
        assignments[kind] = path
        if not isinstance(path, str) or path not in paths:
            errors.append("Unregistered authoritative source: " + repr(path))
        elif not (root / path).is_file() and next((e.get("verification") for e in entries if e.get("path") == path), None) == "required":
            errors.append("Missing authoritative source: " + path)
    policy_file = root / "docs/development-standards.md"
    if policy_file.is_file():
        policy = policy_file.read_text(encoding="utf-8-sig")
        if "### Principal authoritative sources" not in policy:
            errors.append("Missing DevStan principal authoritative sources")
        else:
            section = policy.split("### Principal authoritative sources", 1)[1].split("\n## ", 1)[0]
            declared = {}
            for line in section.splitlines():
                match = re.fullmatch(r"\| ([^|]+?) \| `([^`]+)` \|(?: [^|]* \|)?", line.strip())
                if match:
                    kind, path = match.groups()
                    kind = {"Development Standards": "development-rules", "Functional Specification": "functional-requirements", "Python syntax defect records": "python-syntax-defects", "Development defect records": "development-defects"}.get(kind, kind)
                    if path.startswith(("app-repo:", "standards-repo:")):
                        path = path.split(":", 1)[1]
                    if kind == "central-document-inventory":
                        continue
                    if kind in declared:
                        errors.append("Duplicate DevStan authoritative source: " + kind)
                    declared[kind] = path
            if not declared:
                errors.append("No DevStan authoritative sources defined")
            if "acceptance-test-results" in assignments:
                declared["acceptance-test-results"] = assignments["acceptance-test-results"]
            if declared != assignments:
                errors.append("Authoritative source mappings differ from DevStan")
    # The latest version-history row is authoritative for each versioned document.
    versioned = [entry for entry in entries if entry.get("version_source")]
    for entry in versioned:
        path, source = entry["path"], entry["version_source"]
        if source not in paths:
            errors.append("Unregistered document version source: " + str(source))
            continue
        source_file = root / source
        if not source_file.is_file():
            errors.append("Missing document version source: " + source)
            continue
        content = source_file.read_text(encoding="utf-8-sig")
        if "## Version history" in content:
            history = content.split("## Version history", 1)[1]
        elif "## 10. Change history" in content:
            history = content.split("## 10. Change history", 1)[1]
        else:
            errors.append("Missing document version history: " + source)
            continue
        version = re.search(r"(?m)^\|(?: \d{4}-\d{2}-\d{2} \|)? v(\d+\.\d+) \|", history)
        if not version:
            errors.append("Missing current document version in history: " + source)
        if re.search(r"(?mi)^\*\*(?:Date|Revision date|Document date):\*\*\s*\d{4}-\d{2}-\d{2}", content.split("## ", 1)[0]):
            errors.append("Duplicated document revision date in header: " + source)
        if re.search(r"(?m)^# .*\bv\d+\.\d+\b", content):
            errors.append("Document title contains version: " + source)
    version_authorities = register.get("version_authorities", [])
    if (not isinstance(version_authorities, list) or
        {(x.get("version_type"), x.get("path")) for x in version_authorities if isinstance(x, dict)} !=
        {("application", "config/traceability.json"), ("release", "config/traceability.json")} or
        len(version_authorities) != 2):
        errors.append("Invalid application/release version authority")
    # R02/R07: governing documents and version references must remain aligned.
    required_governance = {"docs/development-standards.md", "docs/functional-specification.md", "README.md", "config/traceability.json"}
    for missing in sorted(required_governance - set(paths)):
        errors.append("Governing document missing from register: " + missing)
    # Current governing references name the source, not a duplicated version.
    for relative, expected in (
        ("AGENTS.md", "docs/development-standards.md"),
        ("docs/functional-specification.md", "docs/development-standards.md"),
    ):
        reference_file = root / relative
        if reference_file.is_file() and expected not in reference_file.read_text(encoding="utf-8-sig"):
            errors.append("Missing authoritative Devstan reference: " + relative)
    spec_file = root / "docs/functional-specification.md"
    if spec_file.is_file():
        spec_text = spec_file.read_text(encoding="utf-8-sig")
        if not re.search(r"(?m)^\*\*Application version:\*\* \x60app-repo:config/traceability.json\x60\s*$", spec_text):
            errors.append("Missing authoritative application version reference")
        if not re.search(r"(?m)^\*\*Document version:\*\* See Section 10, Change history\s*$", spec_text):
            errors.append("Missing authoritative document version history reference")
        if re.search(r"(?m)^\*\*(?:Version|Governing Devstan):\*\*", spec_text):
            errors.append("Duplicated current version declaration in functional specification")
    # Project-specific documents are defined exclusively by the functional specification.
    spec_path = root / "docs/functional-specification.md"
    if spec_path.is_file():
        spec_text = spec_path.read_text(encoding="utf-8-sig")
        heading = "Project-specific controlled document requirements"
        if heading not in spec_text:
            errors.append("Missing authoritative project document table in functional specification")
        else:
            section = re.split(r"(?m)^## \d+\. ", spec_text.split(heading, 1)[1], maxsplit=1)[0]
            expected = {}
            for line in section.splitlines():
                cells = [cell.strip().strip("`").removeprefix("app-repo:") for cell in line.strip().strip("|").split("|")]
                if len(cells) == 4 and re.fullmatch(r"FR-\d{3}", cells[1]):
                    if cells[0] in expected:
                        errors.append("Duplicate specification document: " + cells[0])
                    expected[cells[0]] = (cells[1], cells[2], cells[3])
            if not expected:
                errors.append("No project-specific documents defined in functional specification")
            actual = {entry["path"]: entry for entry in entries if entry.get("requirement")}
            for path, (fr, purpose, status) in expected.items():
                entry = actual.get(path)
                if not entry:
                    errors.append("Specification document missing from register: " + path)
                elif (entry.get("requirement"), entry.get("purpose"), entry.get("verification")) != (fr, purpose, status):
                    errors.append("Project document metadata differs from specification: " + path)
                if not re.search(r"(?m)^- \*\*" + re.escape(fr) + r" \[", spec_text):
                    errors.append("Document references unknown functional requirement: " + fr)
            for path in actual.keys() - expected.keys():
                errors.append("Unsupported project document in register: " + path)
    else:
        errors.append("Missing authoritative functional specification")
    return errors

def produce(root, edition):
    errors = validate(root, check_release_files=True)
    if errors:
        raise ValueError("; ".join(errors))
    rtm = read_json(root / "config/traceability.json")
    devstan_path = root / "release-evidence/devstan.json"
    devstan = read_json(devstan_path) if devstan_path.is_file() else None
    if not isinstance(devstan, dict):
        raise ValueError("Devstan verification JSON required")
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("Git source commit unavailable") from exc
    if devstan.get("source_commit") != head or devstan.get("version") != rtm["version"]:
        raise ValueError("Devstan evidence does not match source commit/version")
    checks = devstan.get("checks", [])
    if len(checks) != 8 or {c.get("rule") for c in checks} != {f"R{i:02d}" for i in range(1, 9)}:
        raise ValueError("Incomplete Devstan verification")
    evidence_dir = root / "release-evidence"
    evidence_dir.mkdir(exist_ok=True)
    files = []
    for entry in read_json(root / "docs/document-register.json")["documents"]:
        if entry["verification"] == "required":
            p = root / entry["path"]
            files.append({"path": entry["path"], "sha256": sha256(p)})
    for path in sorted((root / "tests/results").glob("*.json")):
        if path.suffix == ".json":
            files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256(path)})
    if edition == "production":
        for name in ("info/test-results.pdf", "info/test-evidence.pdf", "info/test-coverage.pdf"):
            file = root / name
            if not file.is_file():
                raise ValueError("Missing production report: " + name)
            files.append({"path": name, "sha256": sha256(file)})
    workbook = root / "info/traceability.xlsx"
    if not workbook.is_file():
        raise ValueError("Missing release traceability workbook: info/traceability.xlsx")
    files.append({"path": "info/traceability.xlsx", "sha256": sha256(workbook)})
    for path in sorted(evidence_dir.glob("*")):
        if path.is_file() and path.name != "evidence-manifest.json":
            files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256(path)})
    for path in sorted((root / "dist").glob("*")) if (root / "dist").is_dir() else []:
        if path.is_file():
            files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256(path)})
    manifest = {
        "schema_version": 1, "application": "virtual-admin", "version": rtm["version"],
        "source_commit": head, "edition": edition,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "devstan_timestamp_utc": devstan.get("timestamp_utc"),
        "devstan_production_ready": devstan.get("production_ready") is True,
        "files": files,
    }
    (evidence_dir / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=pathlib.Path, default=ROOT)
    p.add_argument("--edition", choices=("acceptance", "production"), default="acceptance")
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args()
    try:
        issues = validate(args.root, check_release_files=not args.verify_only)
        if issues:
            raise ValueError("; ".join(issues))
        if args.verify_only:
            print("Controlled document register: PASS")
        else:
            manifest = produce(args.root, args.edition)
            print(f"Evidence manifest: {len(manifest['files'])} files; machine-readable manifest generated")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
