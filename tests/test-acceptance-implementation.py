#!/usr/bin/env python3
"""R03 controlled fixture: inventory-only acceptance tests must fail Preflight."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("implementation", ROOT / "scripts/verify-acceptance-implementation.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ImplementationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for relative in ("config/traceability.json", "tests/test-functional-acceptance.ps1"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def tearDown(self):
        self.tmp.cleanup()

    def test_current_inventory_has_explicit_results(self):
        self.assertEqual(module.verify(self.root), [])

    def test_added_inventory_only_test_is_rejected(self):
        path = self.root / "config/traceability.json"
        inventory = json.loads(path.read_text(encoding="utf-8"))
        row = dict(next(x for x in inventory["acceptance_tests"] if x["id"] == "AT-012"))
        row["id"] = "AT-099"
        inventory["acceptance_tests"].append(row)
        path.write_text(json.dumps(inventory), encoding="utf-8")
        self.assertTrue(any("AT-099" in x for x in module.verify(self.root)))

    def test_removed_recording_path_is_rejected(self):
        path = self.root / "tests/test-functional-acceptance.ps1"
        source = path.read_text(encoding="utf-8")
        self.assertIn("Record 'AT-012' 'PASS'", source)
        path.write_text(source.replace("Record 'AT-012' 'PASS'", "Write-Host 'AT-012' 'PASS'"), encoding="utf-8")
        self.assertTrue(any("AT-012" in x for x in module.verify(self.root)))

if __name__ == "__main__":
    unittest.main()
