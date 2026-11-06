# FR-012: Generate the versioned formatting-checks PDF from authoritative JSON.
"""FR-012: Generate a versioned PDF of implemented formatting checks."""
import hashlib
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, LongTable, TableStyle
rl_config.pageCompression = 0
root = Path(__file__).resolve().parent.parent
raw = (root / "config/format-checks.json").read_bytes()
checks = json.loads(raw.decode("utf-8-sig"))["checks"]
version = json.loads((root / "config/traceability.json").read_text(encoding="utf-8-sig"))["version"]
if not isinstance(version, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
    raise SystemExit("Invalid application version in traceability.json")
ids = [str(c["id"]) for c in checks]
if len(set(ids)) != len(ids):
    raise SystemExit("Duplicate check IDs")
for c in checks:
    if c.get("status") == "planned" and c["enabled"]:
        raise SystemExit("Planned check enabled")
for c in checks:
    if not isinstance(c.get("enabled"), bool):
        raise SystemExit(f"Check {c['id']} enabled must be a boolean")
title = f"Formatting checks for v{version}"
digest = hashlib.sha256(raw).hexdigest()
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CheckCell", parent=styles["BodyText"], fontSize=8, leading=11))
styles.add(ParagraphStyle(name="CheckHeader", parent=styles["CheckCell"], textColor=colors.white))
styles.add(ParagraphStyle(name="CheckTitleLeft", parent=styles["Title"], alignment=0))
rows = [[Paragraph(escape(x), styles["CheckHeader"]) for x in ("Check ID", "Scope", "Property", "Enabled", "Description / Purpose")]]
for c in checks:
    rows.append([Paragraph(escape(str(x)), styles["CheckCell"]) for x in (c["id"], c["scope"], c.get("property", ""), "Y" if c["enabled"] else "", c["description"])])
table = LongTable(rows, colWidths=[78, 95, 120, 65, 414], repeatRows=1)
table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), .3, colors.lightgrey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke])]))
def footer(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.drawString(35, 25, "VA-JSON-SHA256: " + digest)
    canvas.drawRightString(807, 25, "VA-VERSION: " + version)
    canvas.restoreState()
out = root / "info" / "formatting-checks.pdf"
out.parent.mkdir(parents=True, exist_ok=True)
doc = SimpleDocTemplate(str(out), pagesize=(842, 595), leftMargin=35, rightMargin=35, topMargin=40, bottomMargin=42, title=title, pageCompression=0)
doc.build([Paragraph(escape(title), styles["CheckTitleLeft"]), table], onFirstPage=footer, onLaterPages=footer)
print(f"Generated {out.name} for v{version}: {len(checks)} checks")
