#!/usr/bin/env python3
"""Generate release.pdf from Git commits since the preceding application version."""
import re
import json
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parent.parent

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()

def version_at(revision):
    """Read the authoritative application version at a Git revision.

    Older commits used a specification header before traceability.json became
    authoritative; retain that historical fallback only for baseline discovery.
    """
    try:
        data = git("show", revision + ":traceability.json")
        value = json.loads(data).get("version")
        if isinstance(value, str) and re.fullmatch(r"\d+\.\d+", value):
            return value
    except (subprocess.CalledProcessError, ValueError):
        pass
    try:
        text = git("show", revision + ":docs/functional-specification.md")
    except subprocess.CalledProcessError:
        return None
    match = re.search(r"(?m)^\*\*Version:\*\*\s*v?(\d+\.\d+)", text)
    return match.group(1) if match else None

def main():
    current = version_at("HEAD")
    if not current:
        raise SystemExit("Current application version unavailable")
    # Find the most recent preceding version from the actual specification history,
    # even if a previous version was never tagged.
    history = git("rev-list", "HEAD", "--", "traceability.json", "docs/functional-specification.md").splitlines()
    previous = None
    baseline = None
    for sha in history:
        candidate = version_at(sha)
        if candidate and candidate != current:
            previous, baseline = candidate, sha
            break
    if not baseline:
        raise SystemExit("Cannot identify a previous application version from Git history")
    raw = git("log", "--reverse", "--no-merges", "--format=%h%x09%s", baseline + "..HEAD")
    changes = [line.split("\t", 1) for line in raw.splitlines() if "\t" in line]
    if not changes:
        raise SystemExit("No changes since previous application version")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReleaseEntry", parent=styles["BodyText"], spaceAfter=7, leading=12))
    story = [
        Paragraph("Virtual Admin - Release changes", styles["Title"]),
        Paragraph(f"Current version: <b>{escape(current)}</b>", styles["BodyText"]),
        Paragraph(f"Previous version: <b>{escape(previous)}</b>", styles["BodyText"]),
        Paragraph(f"Release source: <b>{escape(git('rev-parse', '--short=12', 'HEAD'))}</b>", styles["BodyText"]),
        Spacer(1, 16),
        Paragraph("Changes since the previous version", styles["Heading2"]),
        Paragraph("The following entries are Git commit summaries, not acceptance-test results.", styles["BodyText"]),
        Spacer(1, 10),
    ]
    for sha, message in changes:
        story.append(Paragraph(f"<b>{escape(sha)}</b> - {escape(message)}", styles["ReleaseEntry"]))
    target = ROOT / "info" / "release.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(target), pagesize=(595, 842), leftMargin=42, rightMargin=42,
                            topMargin=48, bottomMargin=45, title=f"Virtual Admin {current} release changes")
    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.lightgrey)
        canvas.line(42, 35, 553, 35)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 24, f"Virtual Admin {current} - changes since {previous}")
        canvas.drawRightString(553, 24, f"Page {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Generated release.pdf: {previous} -> {current}, {len(changes)} commits")

if __name__ == "__main__":
    main()
