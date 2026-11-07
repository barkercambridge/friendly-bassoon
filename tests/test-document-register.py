#!/usr/bin/env python3
"""Regression tests for the controlled document register."""
import importlib.util
import json
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("document_register", ROOT / "scripts/verify-document-register.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DocumentRegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        src = ROOT / "docs/document-register.json"
        dest = self.root / "docs/document-register.json"
        dest.parent.mkdir(parents=True)
        shutil.copyfile(src, dest)
        self.register = json.loads(src.read_text())
        for item in self.register["documents"]:
            if item["verification"] == "required":
                path = self.root / item["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            elif item["verification"] == "pattern":
                path = self.root / item["path"].replace("*", "sample")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
        spec = ROOT / "docs/functional-specification.md"
        shutil.copyfile(spec, self.root / "docs/functional-specification.md")
        shutil.copyfile(ROOT / "docs/development-standards.md", self.root / "docs/development-standards.md")
        shutil.copyfile(ROOT / "AGENTS.md", self.root / "AGENTS.md")
        shutil.copyfile(ROOT / "README.md", self.root / "README.md")
        for entry in self.register["documents"]:
            if entry.get("version_source") and (ROOT / entry["version_source"]).is_file():
                shutil.copyfile(ROOT / entry["version_source"], self.root / entry["version_source"])
        self.assertEqual(module.validate(self.root), [])

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_authoritative_mapping_fails(self):
        self.register["authoritative_sources"].pop()
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Authoritative source mappings differ" in x for x in module.validate(self.root)))

    def test_duplicate_authoritative_mapping_fails(self):
        self.register["authoritative_sources"].append(dict(self.register["authoritative_sources"][0]))
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Duplicate or invalid authoritative information type" in x for x in module.validate(self.root)))

    def test_conflicting_authoritative_mapping_fails(self):
        self.register["authoritative_sources"][0]["path"] = "README.md"
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Authoritative source mappings differ" in x for x in module.validate(self.root)))

    def test_unregistered_authoritative_source_fails(self):
        self.register["authoritative_sources"][0]["path"] = "docs/unregistered.md"
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Unregistered authoritative source" in x for x in module.validate(self.root)))

    def test_missing_document_version_history_fails(self):
        path = self.root / "docs/functional-specification.md"
        path.write_text("# Functional Specification\\n")
        self.assertTrue(any("Missing document version history" in x for x in module.validate(self.root)))

    def test_invalid_document_version_history_fails(self):
        path = self.root / "docs/functional-specification.md"
        content = path.read_text()
        content, count = re.subn(r"(?m)^(\\| v\\d+\\.\\d+ \\|)", "| invalid |", content, count=1)
        self.assertEqual(count, 1, "Expected a version-history entry to invalidate")
        path.write_text(content)
        self.assertTrue(any("Missing current document version" in x for x in module.validate(self.root)))

    def test_duplicated_revision_date_in_header_fails(self):
        path = self.root / "docs/functional-specification.md"
        path.write_text(path.read_text().replace("**Repository:**", "**Date:** 2026-11-05\\n**Repository:**", 1))
        self.assertTrue(any("Duplicated document revision date in header" in x for x in module.validate(self.root)))

    def test_document_title_version_fails(self):
        path = self.root / "docs/functional-specification.md"
        path.write_text("# Functional Specification v1.0\\n" + path.read_text())
        self.assertTrue(any("Document title contains version" in x for x in module.validate(self.root)))

    def test_release_version_authority_mismatch_fails(self):
        self.register["version_authorities"][1]["path"] = "README.md"
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Invalid application/release version authority" in x for x in module.validate(self.root)))

    def test_missing_governing_document_fails(self):
        (self.root / "docs/development-standards.md").unlink()
        self.assertTrue(any("Missing required document" in x for x in module.validate(self.root)))

    def test_missing_governing_source_reference_fails(self):
        path = self.root / "AGENTS.md"
        path.write_text(path.read_text().replace("docs/development-standards.md", "docs/other-standard.md"))
        self.assertTrue(any("Missing authoritative Devstan reference: AGENTS.md" in x for x in module.validate(self.root)))

    def test_readme_content_is_not_governance_validated(self):
        path = self.root / "README.md"
        path.write_text("# Quick start\\nInstall and run the launcher.\\n")
        self.assertEqual(module.validate(self.root), [])

    def test_missing_application_version_source_fails(self):
        path = self.root / "docs/functional-specification.md"
        path.write_text(path.read_text().replace("**Application version:** `app-repo:config/traceability.json`", "**Application version:** `README.md`"))
        self.assertTrue(any("Missing authoritative application version reference" in x for x in module.validate(self.root)))

    def test_pdf_register_purpose_matches_specification(self):
        entry = next(x for x in self.register["documents"] if x["path"] == "info/formatting-checks.pdf")
        self.assertEqual(entry["requirement"], "FR-012")
        self.assertEqual(entry["purpose"], "Human-readable mirror of formatting configuration")
        self.assertEqual(entry["verification"], "required")

    def test_release_pdf_is_production_only_generated_report(self):
        entry = next(x for x in self.register["documents"] if x["path"] == "info/release.pdf")
        self.assertNotIn("requirement", entry)
        self.assertIn("DevStan R08", entry["authority"])
        self.assertIn("production-only", entry["authority"])
        self.assertEqual(entry["verification"], "generated")
        self.assertEqual(module.validate(self.root), [])

    def test_no_acceptance_evidence_before_first_test_run(self):
        self.assertEqual(module.validate(self.root), [])
        for name in ("virtual-admin-sample.json", "virtual-admin-sample.txt"):
            evidence_path = self.root / "tests/results" / name
            if evidence_path.exists():
                evidence_path.unlink()
        self.assertEqual(module.validate(self.root), [])

    def test_missing_required_file_fails(self):
        (self.root / "README.md").unlink()
        self.assertTrue(any("Missing required" in x for x in module.validate(self.root)))

    def test_duplicate_reference_fails(self):
        self.register["documents"].append(dict(self.register["documents"][0]))
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Duplicate" in x for x in module.validate(self.root)))

    def test_specification_document_missing_from_register_fails(self):
        self.register["documents"] = [x for x in self.register["documents"]
                                      if x["path"] != "info/formatting-checks.pdf"]
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Specification document missing" in x for x in module.validate(self.root)))

    def test_unsupported_project_document_fails(self):
        self.register["documents"].append({
            "path": "config/unknown.json", "role": "unknown", "authority": "unspecified",
            "verification": "required", "requirement": "FR-012", "purpose": "Unspecified"})
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Unsupported project document" in x for x in module.validate(self.root)))

    def test_project_document_purpose_mismatch_fails(self):
        entry = next(x for x in self.register["documents"] if x.get("requirement") == "FR-012")
        entry["purpose"] = "Incorrect purpose"
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("metadata differs" in x for x in module.validate(self.root)))

    def test_path_traversal_fails(self):
        self.register["documents"][0]["path"] = "../private.txt"
        (self.root / "docs/document-register.json").write_text(json.dumps(self.register))
        self.assertTrue(any("Invalid document path" in x for x in module.validate(self.root)))

if __name__ == "__main__":
    unittest.main()
