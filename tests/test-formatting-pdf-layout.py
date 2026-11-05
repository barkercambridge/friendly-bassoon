#!/usr/bin/env python3
"""Guard the PDF register's title alignment and white header text."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent

class PdfLayoutTests(unittest.TestCase):
    def test_title_is_left_aligned(self):
        source = (ROOT / "scripts/build-formatting-checks.py").read_text(encoding="utf-8")
        self.assertIn('name="CheckTitleLeft", parent=styles["Title"], alignment=0', source)
        self.assertIn('Paragraph(escape(title), styles["CheckTitleLeft"])', source)

    def test_all_checks_and_enabled_column(self):
        source = (ROOT / "scripts/build-formatting-checks.py").read_text(encoding="utf-8")
        self.assertIn('for c in checks:\n    rows.append', source)
        self.assertIn('"Y" if c["enabled"] else ""', source)
        self.assertIn('"Enabled", "Description / Purpose"', source)
        self.assertIn('title = f"Formatting checks for v{version}"', source)

    def test_release_version_uses_authoritative_traceability(self):
        source = (ROOT / "scripts/build-formatting-checks.py").read_text(encoding="utf-8")
        self.assertIn('root / "traceability.json"', source)
        self.assertIn('Invalid application version in traceability.json', source)
        self.assertNotIn('Missing release version in functional specification', source)
        self.assertNotIn('**Version:**', source)

    def test_header_paragraphs_are_white(self):
        source = (ROOT / "scripts/build-formatting-checks.py").read_text(encoding="utf-8")
        self.assertIn('name="CheckHeader", parent=styles["CheckCell"], textColor=colors.white', source)
        self.assertIn('Paragraph(escape(x), styles["CheckHeader"])', source)

if __name__ == "__main__":
    unittest.main()
