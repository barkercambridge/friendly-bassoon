# Word formatting checker

Windows proof of concept for comparing a Word document's formatting against an approved example template, highlighting differences in a separate DOCX copy and producing an activity report. Formatting checks are defined in `app-repo:config/format-checks.json`; configuration errors are written to `activity.docx` in the target document directory.

## Quick start
The batch launcher fails with exit code 2 and an error message if either required input is missing from its directory.
Requires Windows, desktop Microsoft Word and Windows PowerShell 5.1. No administrator rights required.

1. Put your approved `.dotx` template and target `.docx` document beside `run-virtual-admin.bat`. If multiple files exist, the launcher selects the first filename alphabetically for each extension.
2. Double-click `run-virtual-admin.bat`.
3. Open the generated `<document name>-HIGHLIGHT.docx` and accompanying `activity.docx`. On each subsequent launch, any previous highlighted DOCX and `activity.docx` are automatically timestamped and moved to `old/` before comparison. If the check specification is missing, invalid or contains an unsupported check, inspect `activity.docx` in the same directory.

For custom document paths, see [installation instructions](docs/installation.md).

## Status
**Current application status: acceptance testing pending; production is not approved.** The current version is defined in `app-repo:config/traceability.json`. Historical results below do not apply to the current implementation.

Windows acceptance testing for v0.2.3 completed on 2026-11-04 against source commit `264cd78e5889a371a512b730bd4610a4900eb1b8`: **10 PASS, 0 FAIL, 0 BLOCKED** (AT-001–AT-008, AT-010, AT-011). The test environment used Windows PowerShell 5.1.26100.9711 and Microsoft Word 16.0. AT-007 is a static launcher check and does not execute the launcher with Word. That historical evidence is not retained under the current single-file policy. This establishes acceptance-test success for the tested source commit, not production approval or completion of Development Standards production gates. The current CHAR-001 check compares each paragraph's font family, size, bold and italic with its matching named style in the template (non-positionally), using a four-property uniform-font fast path. Structural text differences remain reported separately. This new implementation has not yet passed fresh acceptance testing. See [functional specification](docs/functional-specification.md).

## Development standards
The governing [Development Standards](https://github.com/barkercambridge/miniature-memory/blob/main/docs/development-standards.md) and Python and general development defect registers are maintained in the private `barkercambridge/miniature-memory` repository. `app-repo:config/central-standards.json` pins the exact approved commit; Preflight and Release retrieve validated runtime copies using the `STANDARDS_READ_TOKEN` Actions secret (fine-grained, Contents: Read-only, limited to `miniature-memory`). Missing or invalid retrieval blocks verification. Development Standards requires FR/AT traceability, original acceptance evidence, source equivalence, package provenance, and a fail-closed production gate. Central updates do not automatically change the approved pin. Commits require owner authorisation; production approval is recorded automatically only when every mandatory control passes.

## Files
- `app-repo:src/compare-formatting.ps1`: Word COM comparison engine
- `app-repo:config/format-checks.json`: machine-readable implemented and planned formatting checks
- `info/formatting-checks.pdf`: readable PDF formatting-check register, verified against JSON by FR-012
- `run-virtual-admin.bat`: Windows launcher
- `app-repo:docs/functional-specification.md`: FRs and acceptance matrix
- `app-repo:tests/test-functional-acceptance.ps1`: Windows fixture runner (manual checks still required)
- `app-repo:tests/test-format-checks-alignment.ps1`: report-versus-JSON validation
- `app-repo:tests/test-package-archive.ps1`: ZIP layout and report inclusion validation
- `app-repo:config/traceability.json`: authoritative FR-to-source/acceptance-test mappings and RT-001–RT-004 regression-suite mappings

The controlled document inventory is `app-repo:docs/document-register.json`, verified automatically against required files and evidence. Each release workflow generates a run-specific `app-repo:release-evidence/evidence-manifest.json` containing source/version provenance and SHA-256 checksums. The production approval gate checks the manifest before approving publication. Only the current acceptance JSON is retained; prior acceptance results are not kept in the repository. Preflight reports affected evidence as NOT VERIFIED in a separate JSON artifact.

## Automated acceptance evidence (Windows)
Keep the original acceptance ZIP beside its extracted folder (or pass `-AcceptanceZipPath` to `app-repo:tests/test-functional-acceptance.ps1`); the test runner hashes that ZIP and records the same SHA-256 in both JSON evidence files. Run the acceptance package on interactive Windows with Microsoft Word installed. The acceptance runner generates `app-repo:tests/results/acceptance-results.json` and `app-repo:tests/results/code-coverage.json` against the extracted acceptance ZIP. Upload both JSON files together. Upload the original JSON to the same repository path after testing; do not keep historical results. A release-affecting main-branch change invalidates and deletes **all files** in `tests/results/` except for a controlled evidence-only upload. Production requires fresh passing evidence matching the tested source, and generates `info/test-results.pdf`, `info/test-evidence.pdf` and `info/test-coverage.pdf` for the production ZIP.


## Release ZIP layout
Every acceptance and production release includes `app-repo:config/format-checks.json`, `info/formatting-checks.pdf` and `info/release.pdf`. **Only production** generates and includes `info/traceability.xlsx` with verified FR/AT/Development Standards evidence, together with `info/test-results.pdf`, `info/test-evidence.pdf` and `info/test-coverage.pdf`. Acceptance includes source-controlled `app-repo:config/traceability.json` for FR/source/AT mappings and no compiled test-evidence reports. Only Windows batch launchers are placed at the ZIP root; PDF reports are under `info/`. Application scripts are under `src/`, JSON check configuration and `virtual-admin-build.json` under `config/`, and documentation under `docs/`. Acceptance packages additionally contain `run-acceptance-tests.bat` at the ZIP root, with PowerShell test scripts in the `tests/` subfolder. The production package contains `run-virtual-admin.bat`, `info/traceability.xlsx`, `info/formatting-checks.pdf`, `info/release.pdf`, `info/test-results.pdf`, `info/test-evidence.pdf` and `info/test-coverage.pdf` under `info/`, and excludes `run-acceptance-tests.bat` and the entire `tests/` subfolder. ZIP layout and report alignment are verified automatically before a release is accepted. Place the first alphabetically sorted `.dotx` and `.docx` files beside the main launcher after extraction; these inputs are not bundled.

## Release workflow
Use **Actions → `Virtual Admin Release` → Run workflow** and choose **Acceptance Testing** or **Production**. The version is read from `app-repo:config/traceability.json`.

**Acceptance Testing** validates PowerShell syntax and FR/AT mappings, builds the acceptance ZIP and checksum, and publishes an unapproved prerelease. Run `run-acceptance-tests.bat` at the extracted ZIP root on an interactive Windows desktop with Microsoft Word. GitHub-hosted CI does not run Word COM acceptance tests.

**Production** checks original committed acceptance JSON evidence, source equivalence and production ZIP layout/provenance, then runs `scripts/verify-devstan.py --production`. Only if all eight Development Standards rules PASS does `app-repo:scripts/record-production-approval.py` write `app-repo:release-evidence/production-approval.json` with method **Automated verification**, UTC timestamp, tested/release commits and evidence paths. Publication is blocked by any FAIL or NOT VERIFIED. A successful acceptance run alone does not approve production.

The current Development Standards verifier explicitly marks maintainability/security review, operational installation/upgrade verification and documentation semantic review **NOT VERIFIED** without independent evidence. These must be completed before production publication; they are not silently treated as passing. The current evidence is for tested commit `264cd78e5889a371a512b730bd4610a4900eb1b8`; release-affecting changes require new acceptance testing.

### Activity report

Each comparison writes `activity.docx` beside the checked document. Its opening **Errors** section lists checks or attempted comparisons that could not be completed, with diagnostic details; **None** means no such errors. Its final **Summary of changes** section lists formatting and structural differences. The former `*-differences.txt` and `Errors.docx` outputs are no longer generated. Failed checks cause a nonzero exit; the highlighted copy is a separate output.

## Version history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-11-05 | Establish independently versioned controlled document history. |
