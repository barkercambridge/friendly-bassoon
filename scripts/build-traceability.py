# FR-016: Application-specific acceptance and release evidence.
"""Build the FR/AT traceability workbook for release info/ evidence."""
import json
import argparse
from pathlib import Path
import re
from openpyxl import Workbook

parser = argparse.ArgumentParser()
parser.add_argument("--edition", choices=("production",), required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
devstan_text = (root / "docs/development-standards.md").read_text(encoding="utf-8-sig")
match = re.search(r"(?m)^\| \d{4}-\d{2}-\d{2} \| v(\d+\.\d+) \|", devstan_text)
if not match:
    raise ValueError("Devstan version missing")
devstan_version = match.group(1)
rtm = json.loads(Path("config/traceability.json").read_text(encoding="utf-8"))
result_files = [Path("tests/results/acceptance-results.json")] if Path("tests/results/acceptance-results.json").is_file() else []
evidence = json.loads(result_files[-1].read_text(encoding="utf-8-sig")) if args.edition == "production" and result_files else {"tests": []}
standards_path = Path("release-evidence/devstan.json")
standards_report = json.loads(standards_path.read_text(encoding="utf-8-sig")) if standards_path.exists() else {}
standards = standards_report.get("checks", []) if args.edition == "production" else []

wb = Workbook()
requirements = wb.active
requirements.title = "Requirements"
requirements.append(["FR", "Status", "AT required", "INF approval", "Implementation source", "Test implementation", "Coverage instrumentation", "AT"])
for item in rtm["requirements"]:
    status = item.get("status", "active").lower()
    approved_inf = status == "inf" and item.get("inf_approved") is True and bool(item.get("inf_approval_reference"))
    at_required = status != "planned" and not approved_inf
    requirements.append([item["id"], status, "YES" if at_required else "NO",
                         item.get("inf_approval_reference", "") if approved_inf else "",
                         ", ".join(item.get("implementation_source", [])), ", ".join(item.get("test_implementation", [])), ", ".join(item.get("coverage_instrumentation", [])), ", ".join(item.get("tests", []))])

deps = wb.create_sheet("Source Dependencies")
deps.append(["FR", "Classification", "File"])
for item in rtm["requirements"]:
    for role in ("implementation_source", "test_implementation", "coverage_instrumentation"):
        for source in item.get(role, []):
            deps.append([item["id"], role, source])

tests = wb.create_sheet("Test Results") if args.edition == "production" else None
if tests is not None:
    tests.append(["AT", "Status", "Requirements", "Details", "Evidence version", "Source commit"])
for item in evidence.get("tests", []) if tests is not None else []:
    tests.append([item.get("test_id"), item.get("status"), ", ".join(item.get("requirements", [])),
                  item.get("details"), evidence.get("version"), evidence.get("source_commit")])

dashboard = wb.create_sheet("Compliance Dashboard") if args.edition == "production" else None
if dashboard is not None: dashboard.append(["Metric", "Value"])
if dashboard is not None:
    dashboard.append(["Application version", rtm["version"]])
    dashboard.append(["Functional test records", len(evidence.get("tests", []))])
    dashboard.append(["Functional tests passed", evidence.get("passed", 0)])
    dashboard.append(["Functional tests failed", evidence.get("failed", 0)])
    dashboard.append(["Functional tests blocked", evidence.get("blocked", 0)])
    dashboard.append(["Functional evidence source commit", evidence.get("source_commit") or "MISSING"])
    dashboard.append(["Devstan v" + devstan_version + " rules passed", sum(1 for item in standards if item.get("status") == "PASS")])
    dashboard.append(["Devstan v" + devstan_version + " rules failed", sum(1 for item in standards if item.get("status") == "FAIL")])
    dashboard.append(["Devstan v" + devstan_version + " rules not verified", sum(1 for item in standards if item.get("status") == "NOT VERIFIED")])
    dashboard.append(["Overall release readiness", "READY" if standards_report.get("production_ready") is True else "BLOCKED - production verification incomplete"])

compliance = wb.create_sheet("Dev Standards Compliance") if args.edition == "production" else None
if compliance is not None: compliance.append(["Rule", "Result", "Evidence source", "Detail"])
for item in standards:
    compliance.append([item.get("rule"), item.get("status"), item.get("evidence"), item.get("detail")])
if compliance is not None and not standards:
    compliance.append(["Devstan v" + devstan_version + "", "NOT VERIFIED", "release-evidence/devstan.json",
                       "Run scripts/verify-devstan.py to generate current evidence."])

Path("info").mkdir(exist_ok=True)
wb.save("info/traceability.xlsx")
