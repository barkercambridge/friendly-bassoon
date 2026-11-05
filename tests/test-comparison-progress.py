#!/usr/bin/env python3
"""Static regression coverage for the Word comparison progress and COM cache."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parent.parent / "src/compare-formatting.ps1").read_text(encoding="utf-8")

class ComparisonProgressTests(unittest.TestCase):
    def test_progress_and_bounded_runtime(self):
        self.assertIn("[int]$ComparisonTimeoutSeconds = 1800", SOURCE)
        self.assertIn("$totalParagraphs = [Math]::Max(", SOURCE)
        self.assertIn('Write-Stage ("Comparing paragraph {0}/{1}', SOURCE)
        self.assertIn('Write-Stage ("Comparison finished in {0:n1}s', SOURCE)
        self.assertIn("if ($comparisonTimer.Elapsed.TotalSeconds -ge $ComparisonTimeoutSeconds)", SOURCE)
        self.assertIn('$_.Exception -is [System.OperationCanceledException] -or $_.Exception.Message -like "Comparison exceeded $ComparisonTimeoutSeconds seconds*") { throw }', SOURCE)
    def test_escape_cancel_without_interfering_with_noninteractive_runs(self):
        self.assertIn("function Test-UserCancellation", SOURCE)
        self.assertIn("[Console]::IsInputRedirected", SOURCE)
        self.assertIn("[Console]::KeyAvailable", SOURCE)
        self.assertIn("[Console]::ReadKey($true)", SOURCE)
        self.assertIn("[ConsoleKey]::Escape", SOURCE)
        self.assertIn("[System.OperationCanceledException]", SOURCE)
        self.assertIn("Test-UserCancellation", SOURCE)
        self.assertIn("Press Esc to cancel.", SOURCE)

    def test_non_positional_style_font_fast_path(self):
        self.assertIn("function Get-StyleFontProperties($template, $paragraph)", SOURCE)
        self.assertIn("$paragraph.Range.Style.NameLocal", SOURCE)
        self.assertIn("$template.Styles.Item($styleName)", SOURCE)
        for property_name in ("Name", "Size", "Bold", "Italic"):
            self.assertIn("$font." + property_name, SOURCE)
        self.assertIn("function Test-FontProperties($font, $expected)", SOURCE)
        self.assertIn("Test-FontProperties $t.Range.Font $expectedFont", SOURCE)
        self.assertIn("for ($j=1; $j -le $tt.Length; $j++)", SOURCE)
        self.assertIn("Test-FontProperties $character.Font $expectedFont", SOURCE)
        self.assertNotIn("$r.Range.Characters.Item($j)", SOURCE)

    def test_changed_paragraphs_are_reprinted_with_light_blue_marking(self):
        self.assertIn("$changedParagraphs = New-Object", SOURCE)
        self.assertIn("$changedParagraphs.Add(", SOURCE)
        self.assertIn("$marks[$j - 1] = $true", SOURCE)
        self.assertIn('w:fill="ADD8E6"', SOURCE)
        self.assertIn("HighlightColorIndex = 3", SOURCE)
        self.assertNotIn('$findings.Add("$($check.id): paragraph $i character $j', SOURCE)

    def test_activity_summary_table_metrics(self):
        self.assertIn("$summaryTableXml = '<w:tbl>", SOURCE)
        self.assertIn("'Comparison started (UTC)'", SOURCE)
        self.assertIn("'Comparison finished (UTC)'", SOURCE)
        self.assertIn("'Elapsed comparison time'", SOURCE)
        self.assertIn("'Paragraphs compared'", SOURCE)
        self.assertIn("'Total paragraphs'", SOURCE)
        self.assertIn("'Findings'", SOURCE)
        self.assertIn("'Errors'", SOURCE)
        self.assertIn("$processedParagraphs = $i", SOURCE)
        self.assertIn("$comparisonOutcome = 'In progress'", SOURCE)
        self.assertIn("'Cancelled'", SOURCE)

    def test_only_char001_is_configured(self):
        import json
        checks = json.loads((Path(__file__).resolve().parent.parent / "config/format-checks.json").read_text(encoding="utf-8"))["checks"]
        self.assertEqual([c["id"] for c in checks], ["CHAR-001"])
        self.assertTrue(checks[0]["enabled"])
        self.assertIn("$requiredChecks = @('CHAR-001')", SOURCE)

if __name__ == "__main__":
    unittest.main()
