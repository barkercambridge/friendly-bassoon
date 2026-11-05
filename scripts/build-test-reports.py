#!/usr/bin/env python3
# DevStan R08: Compile production-only human-readable acceptance and coverage evidence.
"""DevStan R08: Generate human-readable production reports from acceptance JSON."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {f"AT-{i:03d}" for i in range(1, 9)} | {"AT-010", "AT-011"}

def main():
    data = json.loads((ROOT / "tests/results/acceptance-results.json").read_text(encoding="utf-8-sig"))
    version = json.loads((ROOT / "traceability.json").read_text(encoding="utf-8-sig"))["version"]
    tests = data["tests"]
    if data["version"] != version or len(tests) != 10 or {t["test_id"] for t in tests} != REQUIRED:
        raise ValueError("Invalid acceptance version or test coverage")
    if any(t["status"] != "PASS" for t in tests) or data["passed"] != 10 or data["failed"] or data["blocked"]:
        raise ValueError("Acceptance evidence is not fully passing")
    if not isinstance(data.get("source_commit"), str) or len(data["source_commit"]) != 40:
        raise ValueError("Missing tested source commit")
    styles = getSampleStyleSheet()
    (ROOT / "info").mkdir(exist_ok=True)
    for filename, detail in (("test-results.pdf", False), ("test-evidence.pdf", True)):
        story = [Paragraph("Acceptance test evidence" if detail else "Acceptance test results", styles["Title"])]
        for key in ("version", "source_commit", "run_id", "timestamp_utc", "word_version", "package_sha256"):
            story.append(Paragraph(key + ": " + str(data.get(key, "not recorded")), styles["Normal"]))
        story.append(Spacer(1, 12))
        for test in sorted(tests, key=lambda t: t["test_id"]):
            story.append(Paragraph(test["test_id"] + ": " + test["status"], styles["Heading3"]))
            if detail:
                description = str(test.get("details", "not recorded"))
                story.append(Paragraph(description.replace("&", "&amp;").replace("<", "&lt;"), styles["Normal"]))
        SimpleDocTemplate(str(ROOT / "info" / filename)).build(story)
    coverage = json.loads((ROOT / "tests/results/code-coverage.json").read_text(encoding="utf-8-sig"))
    if coverage.get("version") != version or coverage.get("source_commit") != data["source_commit"]:
        raise ValueError("Coverage evidence provenance mismatch")
    if not isinstance(coverage.get("files"), list) or not coverage["files"]:
        raise ValueError("Coverage file inventory missing")
    story = [Paragraph("Acceptance code test coverage", styles["Title"]),
             Paragraph("Version: " + escape(version), styles["Normal"]),
             Paragraph("Tested commit: " + escape(data["source_commit"]), styles["Normal"]),
             Paragraph("Measurement: " + escape(str(coverage.get("coverage_method", "unknown"))), styles["Normal"]),
             Spacer(1, 12)]
    for file in coverage["files"]:
        path = str(file.get("path", "unknown"))
        measured = file.get("measurement") == "MEASURED"
        covered = file.get("covered_lines", [])
        executable = file.get("executable_lines", [])
        uncovered = file.get("uncovered_lines", [])
        story.append(Paragraph(escape(path) + " — " + ("MEASURED" if measured else "NOT MEASURED"), styles["Heading3"]))
        story.append(Paragraph("Executed statement lines: " + str(len(covered)) +
                               " / " + str(len(executable)) +
                               "; unexecuted: " + str(len(uncovered)), styles["Normal"]))
        if uncovered:
            story.append(Paragraph("Unexecuted line numbers: " + escape(", ".join(map(str, uncovered))), styles["Normal"]))
        if not measured:
            story.append(Paragraph(escape(str(file.get("reason", "Execution not measured"))), styles["Normal"]))
    SimpleDocTemplate(str(ROOT / "info/test-coverage.pdf")).build(story)


if __name__ == "__main__":
    main()
