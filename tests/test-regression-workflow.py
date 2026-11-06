#!/usr/bin/env python3
"""Guard against regression runs rewriting controlled documentation (Devstan R07)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/release.yml"
SPEC = ROOT / "docs/functional-specification.md"

class RegressionWorkflowTests(unittest.TestCase):
    def test_mandatory_workflows_and_independent_freshness_gate(self):
        preflight = (ROOT / ".github/workflows/preflight.yml").read_text(encoding="utf-8")
        release = WORKFLOW.read_text(encoding="utf-8")
        self.assertFalse((ROOT / ".github/workflows/invalidate-acceptance.yml").exists())
        self.assertIn("branches: [main]", preflight)
        self.assertIn("acceptance-evidence-freshness.py --clean-stale-workspace", preflight)
        self.assertIn("reuse-preflight-evidence.py", release)
        self.assertIn("acceptance-evidence-freshness.py", release)
        self.assertIn("inputs.edition == 'Production'", release)

    def test_fingerprint_preserves_editorial_changes_and_rejects_source_changes(self):
        import importlib.util
        import json
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
            git("init")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Preflight Test")
            (root / "src").mkdir()
            (root / "src/app.ps1").write_text("first", encoding="utf-8")
            (root / "README.md").write_text("original", encoding="utf-8")
            git("add", ".")
            git("commit", "-m", "initial")
            tested = git("rev-parse", "HEAD")
            spec = importlib.util.spec_from_file_location("freshness", ROOT / "scripts/acceptance-evidence-freshness.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.ROOT = root
            module.RESULTS = root / "tests/results"
            module.POLICY_PATH = ROOT / "config/release-input-exemptions.json"
            module.RESULTS.mkdir(parents=True)
            for name in ("acceptance-results.json", "code-coverage.json"):
                (module.RESULTS / name).write_text(json.dumps({"source_commit": tested, "release_input_fingerprint": module.fingerprint(tested)}), encoding="utf-8")
            self.assertEqual(module.freshness()[0], "VALID")
            (root / "README.md").write_text("editorial", encoding="utf-8")
            git("add", "README.md")
            git("commit", "-m", "editorial")
            self.assertEqual(module.freshness()[0], "VALID")
            (root / "src/app.ps1").write_text("changed", encoding="utf-8")
            git("add", "src/app.ps1")
            git("commit", "-m", "source")
            self.assertEqual(module.freshness()[0], "STALE")
            (root / "src/app.ps1").write_text("first", encoding="utf-8")
            git("add", "src/app.ps1")
            git("commit", "-m", "restore")
            self.assertEqual(module.freshness()[0], "VALID")
            (module.RESULTS / "code-coverage.json").unlink()
            self.assertEqual(module.freshness()[0], "INVALID")

    def test_generated_results_directory_does_not_change_fingerprint(self):
        import importlib.util
        import subprocess
        import tempfile
        import json
        policy = json.loads((ROOT / "config/release-input-exemptions.json").read_text())
        self.assertEqual(policy["evidence_directory"], "tests/results/")
        self.assertEqual(set(policy["evidence_paths"]), {"tests/results/acceptance-results.json", "tests/results/code-coverage.json"})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Test")
            (root / "src").mkdir()
            (root / "src/app.ps1").write_text("source")
            git("add", ".")
            git("commit", "-qm", "base")
            spec = importlib.util.spec_from_file_location("freshness_exact", ROOT / "scripts/acceptance-evidence-freshness.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.ROOT = root
            module.POLICY_PATH = ROOT / "config/release-input-exemptions.json"
            before = module.fingerprint(git("rev-parse", "HEAD"))
            (root / "tests/results").mkdir(parents=True)
            (root / "tests/results/extra.json").write_text("{}")
            git("add", ".")
            git("commit", "-qm", "extra")
            self.assertEqual(before, module.fingerprint(git("rev-parse", "HEAD")))
            (root / "tests/results/extra.json").write_text('{"new":true}')
            git("add", ".")
            git("commit", "-qm", "updated diagnostics")
            self.assertEqual(before, module.fingerprint(git("rev-parse", "HEAD")))
            (root / "src/app.ps1").write_text("changed")
            git("add", ".")
            git("commit", "-qm", "controlled input")
            self.assertNotEqual(before, module.fingerprint(git("rev-parse", "HEAD")))

    def test_regression_step_only_writes_run_artifacts(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        start = workflow.index("      - name: Validate preflight evidence provenance")
        end = workflow.index("      - name: Verify Devstan FR and AT mappings", start)
        step = workflow[start:end]
        self.assertIn("release-evidence/regression-results.json", step)
        self.assertIn("release-evidence/powershell-syntax.json", step)
        self.assertIn("$regression.source_commit -cne $expected", step)
        self.assertIn("$syntax.source_commit -cne $expected", step)
        self.assertNotIn("sync-regression-spec.py", step)
        self.assertNotIn("git commit", step)
        self.assertNotIn("git push", step)

    def test_release_reuses_only_matching_successful_push_preflight(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        reuse = (ROOT / "scripts/reuse-preflight-evidence.py").read_text(encoding="utf-8")
        self.assertNotIn("uses: ./.github/workflows/preflight.yml", workflow)
        self.assertIn("python scripts/reuse-preflight-evidence.py", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn('run.get("head_sha") == sha', reuse)
        self.assertIn('run.get("event") == "push"', reuse)
        self.assertIn('run.get("head_branch") == "main"', reuse)
        self.assertIn('run.get("conclusion") != "success"', reuse)
        self.assertIn('evidence.get("source_commit") != sha', reuse)
        self.assertIn('gh("run", "download"', reuse)
        ast.parse(reuse)

    def test_source_equivalence_regression_is_mandatory_in_release_workflow(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        start = workflow.index("      - name: Regression-test Git source equivalence policy")
        end = workflow.index("      - name: Validate controlled document register", start)
        step = workflow[start:end]
        self.assertIn("shell: powershell", step)
        self.assertIn("test-git-equivalence.ps1", step)
        self.assertIn("git-equivalence-regression.json", step)
        self.assertIn("$report.failed -ne 0", step)
        self.assertIn("$report.passed -lt 12", step)
        self.assertNotIn("continue-on-error", step)

    def test_git_equivalence_evidence_survives_disposable_repository(self):
        script = (ROOT / "tests/test-git-equivalence.ps1").read_text(encoding="utf-8")
        absolute = "$EvidenceDir=(Resolve-Path -LiteralPath $EvidenceDir).Path"
        self.assertIn(absolute, script)
        self.assertLess(script.index(absolute), script.index("Push-Location $root"))
        self.assertIn("Pop-Location", script)
        self.assertLess(script.index("Pop-Location"), script.index("Remove-Item -LiteralPath $root -Recurse -Force"))
        self.assertIn("Join-Path $EvidenceDir 'git-equivalence-regression.json'", script)

    def test_source_equivalence_allows_only_current_acceptance_upload(self):
        policy = (ROOT / "scripts/verify-source-equivalence.ps1").read_text(encoding="utf-8")
        self.assertIn("$allowed=@($policy.evidence_paths)", policy)
        self.assertIn("$Path.StartsWith([string]$policy.evidence_directory", policy)
        self.assertNotIn("if($Path -like '.github/workflows/*')", policy)
        self.assertIn("$editorial=@($policy.editorial_paths)", policy)
        self.assertIn("if(-not $administrative){$invalid+=$path}", policy)

    def test_single_file_acceptance_contract_in_preflight(self):
        preflight = (ROOT / "scripts/preflight.py").read_text(encoding="utf-8")
        self.assertIn('acceptance-results.json', preflight)
        self.assertIn('Historical or unexpected acceptance evidence found', preflight)
        self.assertNotIn('cleanup-test-results.py', preflight)

    def test_clean_repository_release_notes_have_baseline_fallback(self):
        notes = (ROOT / "scripts/build-release-notes.py").read_text(encoding="utf-8")
        self.assertIn("if baseline:", notes)
        self.assertIn("changes = []", notes)
        self.assertIn("Baseline release: no earlier application version", notes)
        self.assertNotIn('raise SystemExit("Cannot identify a previous application version from Git history")', notes)
        import json
        version = json.loads((ROOT / "config/traceability.json").read_text(encoding="utf-8"))["version"]
        self.assertRegex(version, r"^\d+\.\d+$")

    def test_release_pdf_is_production_only(self):
        package = (ROOT / "scripts/package-release.ps1").read_text(encoding="utf-8")
        archive = (ROOT / "tests/test-package-archive.ps1").read_text(encoding="utf-8")
        acceptance = (ROOT / "tests/test-functional-acceptance.ps1").read_text(encoding="utf-8")
        common = package.split("$commonFiles = @(", 1)[1].split("\n)", 1)[0]
        self.assertNotIn("'info/release.pdf'", common)
        self.assertIn("'run-virtual-admin.bat', 'info/release.pdf', 'info/traceability.xlsx'", package)
        self.assertIn("Acceptance ZIP must not contain release.pdf", archive)
        self.assertIn("Expected exactly one release.pdf in production info/", archive)
        self.assertIn("Acceptance package must not contain production-only release.pdf", acceptance)

    def test_release_uses_one_packager_and_production_verifier(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('package-release.ps1 -Edition production', workflow)
        self.assertIn('verify-production-approval.ps1', workflow)
        self.assertNotIn('package-production.ps1', workflow)
        self.assertNotIn("ChangeExtension($file.FullName, '.txt')", workflow)

    def test_regression_evidence_remains_json_only(self):
        recorder = (ROOT / "scripts/preflight.py").read_text(encoding="utf-8")
        self.assertIn("regression-results.json", recorder)
        self.assertIn("json.dumps(report", recorder)
        preflight_workflow = (ROOT / ".github/workflows/preflight.yml").read_text(encoding="utf-8")
        self.assertNotIn("record-regression-evidence.py", preflight_workflow)
        for name in ("preflight.yml", "release.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertNotIn("sync-regression-spec.py", workflow)

    def test_excel_traceability_is_packaged(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        packager = (ROOT / "scripts/package-release.ps1").read_text(encoding="utf-8")
        self.assertNotIn('python scripts/build-traceability.py --edition acceptance', workflow)
        self.assertIn('python scripts/build-traceability.py --edition production', workflow)
        self.assertLess(workflow.index('Verify current acceptance JSON and tested-source equivalence'), workflow.index('Compile production Excel test evidence'))
        self.assertIn("$files = $commonFiles + @('run-virtual-admin.bat', 'info/release.pdf', 'info/traceability.xlsx'", packager)
        self.assertNotIn("    'info/traceability.xlsx',", packager.split('$commonFiles = @(', 1)[1].split(')', 1)[0])
        self.assertGreater(workflow.index('python scripts/build-traceability.py'), workflow.index('Verify current acceptance JSON and tested-source equivalence'))
        self.assertNotIn('Generate acceptance evidence manifest', workflow)
        self.assertIn('info/test-coverage.pdf', packager)
        self.assertIn('tests/measure-code-coverage.ps1', packager)
        self.assertIn('tests/compile-code-coverage.ps1', packager)

    def test_final_manifest_gate_and_acceptance_zip_provenance(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        verifier = (ROOT / "scripts/verify-final-evidence-manifest.py").read_text(encoding="utf-8")
        acceptance = (ROOT / "tests/test-functional-acceptance.ps1").read_text(encoding="utf-8")
        coverage = (ROOT / "tests/compile-code-coverage.ps1").read_text(encoding="utf-8")
        self.assertIn("python scripts/verify-final-evidence-manifest.py", workflow)
        self.assertIn("release-evidence/production-approval.json", verifier)
        self.assertIn("acceptance_zip_sha256", acceptance)
        self.assertIn("acceptance_zip_sha256", coverage)

    def test_coverage_is_required_for_production_and_invalidated_on_changes(self):
        verifier = (ROOT / "scripts/verify-production-approval.ps1").read_text(encoding="utf-8")
        preflight_workflow = (ROOT / ".github/workflows/preflight.yml").read_text(encoding="utf-8")
        freshness = (ROOT / "scripts/acceptance-evidence-freshness.py").read_text(encoding="utf-8")
        reports = (ROOT / "scripts/build-test-reports.py").read_text(encoding="utf-8")
        packager = (ROOT / "scripts/package-release.ps1").read_text(encoding="utf-8")
        self.assertIn("tests/results/code-coverage.json", verifier)
        self.assertIn("coverage source hash differs", verifier)
        self.assertIn("acceptance-evidence-freshness.py --clean-stale-workspace", preflight_workflow)
        self.assertIn("fingerprint(tested)", freshness)
        self.assertIn("fingerprint(current)", freshness)
        self.assertIn("acceptance-evidence-freshness.py", WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn("info/test-coverage.pdf", packager)
        self.assertIn("info/test-coverage.pdf", reports)
        self.assertIn('glob("*.json")', (ROOT / "scripts/verify-document-register.py").read_text(encoding="utf-8"))
        self.assertIn("compile-code-coverage.ps1", (ROOT / "tests/test-functional-acceptance.ps1").read_text(encoding="utf-8"))
        self.assertIn("archive-coverage", (ROOT / "tests/test-functional-acceptance.ps1").read_text(encoding="utf-8"))
        self.assertIn("archive-*.hits", (ROOT / "tests/compile-code-coverage.ps1").read_text(encoding="utf-8"))

    def test_production_approval_writer_has_valid_python_syntax(self):
        """Catch approval-script syntax errors before production packaging."""
        script = ROOT / "scripts/record-production-approval.py"
        ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python scripts/record-production-approval.py", workflow)

    def test_verifier_and_approval_use_current_governing_devstan_version(self):
        """Release evidence and approval must derive the same live Devstan version."""
        devstan = (ROOT / "docs/development-standards.md").read_text(encoding="utf-8")
        self.assertRegex(devstan, r"(?m)^\| \d{4}-\d{2}-\d{2} \| v\d+\.\d+ \|")
        verifier = (ROOT / "scripts/verify-devstan.py").read_text(encoding="utf-8")
        approval = (ROOT / "scripts/record-production-approval.py").read_text(encoding="utf-8")
        self.assertIn("standard_version=governing_devstan_version()", verifier)
        self.assertIn('report.get("standard_version") != governing_devstan_version()', approval)
        self.assertNotIn('standard_version="5.1"', verifier)
        self.assertNotIn('report.get("standard_version") != "5.0"', approval)
        ast.parse(verifier)
        ast.parse(approval)

    def test_production_verifier_uses_current_acceptance_inventory(self):
        verifier = (ROOT / "scripts/verify-production-approval.ps1").read_text(encoding="utf-8")
        self.assertIn("'config/traceability.json'", verifier)
        self.assertIn("$rtm.acceptance_tests", verifier)
        self.assertIn("$required.Count", verifier)
        self.assertNotIn("$e.passed -ne 10", verifier)
        self.assertIn("'coverage-diagnostics.json'", verifier)
        self.assertIn("$d.source_commit -cne $e.source_commit", verifier)
        self.assertIn("$entries[0].invalid_hit_count -ne 0", verifier)
        self.assertIn("$c.release_input_fingerprint -cne $e.release_input_fingerprint", verifier)

    def test_report_and_approval_use_authoritative_acceptance_inventory(self):
        import importlib.util
        import json
        import tempfile
        from unittest.mock import patch
        scripts = ("build-test-reports", "record-production-approval")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            inventory = {"acceptance_tests": [
                {"id": "AT-101", "stage": "Acceptance", "status": "required"},
                {"id": "AT-102", "stage": "Acceptance", "status": "required"},
                {"id": "AT-999", "stage": "Production", "status": "required"}]}
            (root / "config/traceability.json").write_text(json.dumps(inventory), encoding="utf-8")
            for name in scripts:
                spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / (name + ".py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with patch.object(module, "ROOT", root):
                    self.assertEqual(module.required_acceptance_ids(), {"AT-101", "AT-102"})
                    inventory["acceptance_tests"].append({"id": "AT-103", "stage": "Acceptance", "status": "required"})
                    (root / "config/traceability.json").write_text(json.dumps(inventory), encoding="utf-8")
                    self.assertEqual(module.required_acceptance_ids(), {"AT-101", "AT-102", "AT-103"})
                    inventory["acceptance_tests"].append({"id": "AT-103", "stage": "Acceptance", "status": "required"})
                    (root / "config/traceability.json").write_text(json.dumps(inventory), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        module.required_acceptance_ids()
                    inventory["acceptance_tests"] = inventory["acceptance_tests"][:3]
                    (root / "config/traceability.json").write_text(json.dumps(inventory), encoding="utf-8")

    def test_production_approval_records_per_rule_evidence(self):
        approval = (ROOT / "scripts/record-production-approval.py").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts/verify-final-evidence-manifest.py").read_text(encoding="utf-8")
        self.assertIn('"mandatory_rule_evidence"', approval)
        self.assertIn('mandatory rule evidence references or verification details missing', approval)
        self.assertIn('Production approval lacks complete attributable Devstan rule evidence', verifier)
        ast.parse(approval)
        ast.parse(verifier)

if __name__ == "__main__":
    unittest.main()
