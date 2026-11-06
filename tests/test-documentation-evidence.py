#!/usr/bin/env python3
"""Regression tests for direct JSON acceptance evidence verification."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("alignment", ROOT / "scripts/verify-documentation-evidence.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in ("docs/functional-specification.md", "docs/development-standards.md", "config/traceability.json"):
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        self.version = json.loads((self.root / "config/traceability.json").read_text())["version"]
        self.evidence = self.root / "tests/results/acceptance-results.json"
        self.evidence.parent.mkdir(parents=True)
        mapping = {}
        spec_text = (self.root / "docs/functional-specification.md").read_text()
        for line in spec_text.split("## 5. Acceptance test matrix", 1)[1].split("\n## ", 1)[0].splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4 and cells[0].startswith("AT-"):
                if "[Pending]" not in cells[0]:
                    mapping[cells[0]] = [x.strip() for x in cells[1].split(",")]
        self.data = {"application": "virtual-admin", "version": self.version,
                     "source_commit": "a" * 40, "acceptance_zip_sha256": "b" * 64, "passed": len(mapping), "failed": 0, "blocked": 0,
                     "tests": [{"test_id": k, "requirements": v, "status": "PASS"} for k,v in mapping.items()]}
        self.save()
        self.coverage = self.root / 'tests/results/code-coverage.json'
        self.coverage.write_text(json.dumps({'schema_version': 1, 'application': 'virtual-admin', 'version': self.version, 'source_commit': 'a' * 40, 'acceptance_zip_sha256': 'b' * 64, 'files': [{'path': 'src/archive-previous-outputs.ps1', 'measurement': 'MEASURED', 'covered_lines': [1], 'executable_lines': [1], 'uncovered_lines': []}, {'path': 'src/compare-formatting.ps1', 'measurement': 'MEASURED', 'covered_lines': [1], 'executable_lines': [1], 'uncovered_lines': []}]}))
    def tearDown(self):
        self.tmp.cleanup()
    def save(self):
        self.evidence.write_text(json.dumps(self.data), encoding="utf-8")
    def test_valid_json_passes_without_markdown_register(self):
        self.assertEqual(checker.verify(self.root, production=True), [])
        self.assertFalse((self.root / "docs/test-results.md").exists())
    def test_mismatched_acceptance_zip_checksum_blocks_production(self):
        self.data["acceptance_zip_sha256"] = "c" * 64
        self.save()
        self.assertTrue(any("ZIP SHA-256" in x for x in checker.verify(self.root, production=True)))

    def test_unmeasured_archive_helper_blocks_production(self):
        data = json.loads(self.coverage.read_text())
        data["files"][0]["measurement"] = "NOT MEASURED"
        self.coverage.write_text(json.dumps(data))
        self.assertTrue(any("archive-previous-outputs.ps1" in x for x in checker.verify(self.root, production=True)))

    def test_missing_evidence_blocks_production_not_acceptance_build(self):
        self.evidence.unlink()
        self.coverage.unlink()
        self.assertEqual(checker.verify(self.root, acceptance_build=True), [])
        self.assertTrue(any("No acceptance JSON" in x for x in checker.verify(self.root, production=True)))
    def test_missing_code_coverage_blocks_production(self):
        self.coverage.unlink()
        self.assertTrue(any('code coverage' in x for x in checker.verify(self.root, production=True)))
    def test_stale_code_coverage_blocks_production(self):
        data = json.loads(self.coverage.read_text())
        data['source_commit'] = 'b' * 40
        self.coverage.write_text(json.dumps(data))
        self.assertTrue(any('coverage tested commit' in x for x in checker.verify(self.root, production=True)))
    def test_fail_blocks_production(self):
        self.data["tests"][0]["status"] = "FAIL"
        self.data["passed"] -= 1
        self.data["failed"] = 1
        self.save()
        self.assertTrue(any("Production requires" in x for x in checker.verify(self.root, production=True)))
    def test_duplicate_test_ids_fail(self):
        self.data["tests"][1]["test_id"] = self.data["tests"][0]["test_id"]
        self.save()
        self.assertTrue(any("duplicate AT IDs" in x for x in checker.verify(self.root)))
    def test_wrong_mapping_fails(self):
        self.data["tests"][0]["requirements"] = ["FR-999"]
        self.save()
        self.assertTrue(any("requirements differ" in x for x in checker.verify(self.root)))
    def test_missing_source_commit_fails(self):
        self.data["source_commit"] = None
        self.save()
        self.assertTrue(any("source commit" in x for x in checker.verify(self.root)))
    def test_wrong_totals_fail(self):
        self.data["passed"] = 9
        self.save()
        self.assertTrue(any("totals" in x for x in checker.verify(self.root)))
    def test_application_version_source_reference_fails(self):
        path = self.root / "docs/functional-specification.md"
        path.write_text(path.read_text().replace("`app-repo:config/traceability.json`", "`README.md`", 1))
        self.assertTrue(any("authoritative application version reference missing" in x for x in checker.verify(self.root)))

    def test_governing_devstan_source_reference_fails(self):
        path = self.root / "docs/functional-specification.md"
        path.write_text(path.read_text().replace("**Governing development standard:** `app-repo:docs/development-standards.md`", "**Governing development standard:** `docs/other.md`", 1))
        self.assertTrue(any("governing Devstan source reference missing or invalid" in x for x in checker.verify(self.root)))

if __name__ == "__main__":
    unittest.main()
