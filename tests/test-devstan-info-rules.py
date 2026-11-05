#!/usr/bin/env python3
"""Regression checks for eight mandatory Devstan controls."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("devstan", ROOT / "scripts/verify-devstan.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MandatoryRulesTests(unittest.TestCase):
    def test_exactly_eight_numbered_controls(self):
        for production in (False, True):
            with self.subTest(production=production):
                _, checks = module.check(production=production)
                self.assertEqual(
                    {row["rule"] for row in checks},
                    {f"R{i:02d}" for i in range(1, 9)},
                )
                self.assertEqual(len(checks), 8)

    def test_no_automatic_info_passes(self):
        _, checks = module.check(production=False)
        for row in checks:
            self.assertNotIn("INFO ONLY", row["detail"])
            self.assertNotIn("INFO;", row["evidence"])

    def test_failed_prerequisites_block_production(self):
        _, checks = module.check(production=True)
        by_rule = {row["rule"]: row for row in checks}
        self.assertIn("info/traceability.xlsx", by_rule["R08"]["evidence"])
        for prerequisite in ("R03", "R08"):
            with self.subTest(prerequisite=prerequisite):
                if by_rule[prerequisite]["status"] != "PASS":
                    self.assertNotEqual(by_rule["R06"]["status"], "PASS")
                    self.assertNotEqual(by_rule["R07"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
