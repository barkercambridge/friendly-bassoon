# Functional Specification

**Application version:** `app-repo:config/traceability.json`
**Document version:** See Section 10, Change history

**Repository:** barkercambridge/friendly-bassoon  
**Governing development standard:** `app-repo:docs/development-standards.md`  
**Status:** Functional requirements and acceptance criteria are defined here. Acceptance-test results are uploaded as machine-readable JSON to `app-repo:tests/results/`; no separate test-results document is maintained.

This specification is the authoritative source for application-specific packaging, testing, reporting, runtime, file structure and deliverable requirements. The central Development Standards govern common development, verification, evidence integrity, approval and release controls. The `app-repo:docs/development-standards.md` path is a verified runtime copy retrieved from private `barkercambridge/miniature-memory` at the exact commit pinned in `app-repo:config/central-standards.json`; it is not maintained independently in this repository.



## 1. Purpose and scope

Compare a Word document with an approved DOTX template, produce a highlighted copy of formatting differences and generate an `activity.docx` report. Detailed comparison, output and error-handling requirements are defined in FR-004, FR-005 and FR-011.

## 2. Operating environment
Windows desktop, locally installed Microsoft Word with COM automation, Windows PowerShell 5.1, normal interactive user privileges. Word must be available to the signed-in user. No administrator rights, Python, server, NAS or internet connection required for document comparison.

## 3. Functional requirements
- **FR-001 [Implemented]** Accept template and document paths.
- **FR-002 [Implemented]** The launcher shall select the first `.dotx` file in alphabetical filename order from the same directory as `run-virtual-admin.bat` as the approved template. If none exists, it shall exit unsuccessfully with an error.
- **FR-003 [Implemented]** After archiving previous outputs, the launcher shall select the first `.docx` file in alphabetical filename order from the same directory as `run-virtual-admin.bat` as the document to check. If none exists, it shall exit unsuccessfully with an error.
- **FR-004 [Implemented]** Compare only CHAR-001 (font family, point size, bold and italic) against the corresponding properties defined for each target paragraph's named style in the template, regardless of paragraph position or wording. Skip per-character inspection only when the entire target paragraph has definite uniform matching values for all four properties; otherwise highlight each character where any property differs, using turquoise (light-blue) highlighting. Retain separate structural text and paragraph-count difference reporting. Create a highlighted copy named by inserting `-HIGHLIGHT` immediately before the original document's `.docx` extension, preserving the remainder of the filename and extension.
- **FR-005 [Implemented]** Generate one Word report named `activity.docx` in the same directory as the document being checked. This report shall begin with a two-column summary table recording status, UTC comparison start and finish, elapsed comparison seconds, paragraphs processed and total paragraphs, findings and errors. When a comparison fails or is cancelled, available partial metrics shall be retained and unavailable metrics identified. The existing Errors section and final Summary of changes section shall follow. No separate text-based differences report shall be generated.
- **FR-006 [Implemented]** Preserve the original template and source document without modification. Before selecting the input DOCX, the batch launcher shall move any existing `activity.docx` and any `*-HIGHLIGHT.docx` or `*-HIGHLIGHTED.docx` in the launcher's directory into its `old` subdirectory, creating that directory when required. Append a local date-time stamp to each archived filename, preserving the `.docx` extension; prevent archive name collisions without overwriting existing files. If archival fails, stop unsuccessfully before comparison. The comparison engine shall continue to refuse to overwrite an existing output as a final safety check.
- **FR-007 [Implemented]** Run Microsoft Word Interop only as a normal interactive Windows desktop user. Do not execute Word automation in a noninteractive server session.
- **FR-008 [Planned]** Support reliable comparison of differently structured documents, including tables, sections, headers and footers.
- **FR-009 [Implemented]** Identify text or paragraph-count differences as structural differences rather than guessing positional formatting matches.
- **FR-010 [Implemented]** The batch launcher shall display an error and return a nonzero exit code if either required file is missing from its own directory; it shall not run the comparison in that case.
- **FR-011 [Implemented]** The `activity.docx` report shall contain two sections in order: **Errors** first, listing attempted formatting checks or comparisons that could not be completed, including the check ID, attempted comparison, affected document location and reason where available; display **None** when no errors occurred. **Summary of changes** shall be the final section and list all detected formatting and structural differences (not changes applied to the document), reproducing each affected paragraph once in full, with differing character runs shaded light blue. Paragraph-level or structural differences shade the whole paragraph. Do not list individual character differences or per-property diagnostics in the changes section; display **No differences recorded** if none were detected. Both sections shall be generated even if some checks fail, and successfully detected differences shall be retained. Any failed comparison check shall cause an unsuccessful exit without reporting success.
- **FR-012 [Implemented; pending acceptance verification]** Generate `info/formatting-checks.pdf` as a readable report of **all** checks defined in `app-repo:config/format-checks.json`, including the sole configured CHAR-001 check. The PDF title shall be **Formatting checks for v<release version>**, where `<release version>` is the current application version from `app-repo:config/traceability.json`. Include every check in JSON order. Provide an **Enabled** column containing `Y` when the JSON boolean `enabled` is `true` and a blank cell when it is `false`. The title is left-aligned and table header text is white. An automated alignment check shall verify the report title/version and every check's ID, scope, property, enabled state and description against the JSON, reject missing, extra, duplicate or inconsistent records, and return a nonzero result for any mismatch. A missing JSON status for an enabled check is interpreted as `implemented`; `planned` checks must be disabled. The JSON remains authoritative. The PDF must be regenerated and verified for each release.
- **FR-013 [Implemented; verification pending]** Windows acceptance and regression tests shall validate PowerShell 5.1 syntax and encoding, including complete modified scripts, on the supported runtime. Tests requiring Word COM shall run on an interactive Windows desktop with Microsoft Word installed. Acceptance packages shall include the Windows batch acceptance runner, test scripts, coverage instrumentation, machine-readable traceability and required application files. The authoritative current acceptance evidence shall be `app-repo:tests/results/acceptance-results.json`, recording tested version/commit, release-input fingerprint, package identity and SHA-256, UTC time, environment, individual AT results and diagnostics; historical acceptance JSON shall not be retained as current evidence. Separate regression diagnostics shall remain distinguishable from acceptance evidence.
- **FR-014 [Implemented; verification pending]** Measure executable PowerShell application code under `src/` and identify executable launchers and supporting scripts outside `src/` as measured, not measured or excluded with reasons. Record authoritative coverage at `app-repo:tests/results/code-coverage.json`, including release-input fingerprint, measured statements, executed/unexecuted lines, percentages and exclusions. Instrumentation failures shall produce actionable file-level diagnostics. Coverage hits must demonstrate actual application execution rather than only probe-file creation.
- **FR-015 [Implemented; verification pending]** Produce separate acceptance and production ZIP editions. Only Windows `.bat` launchers shall appear at the ZIP root; other files shall be organised into `src/`, `config/`, `docs/`, `tests/` and `info/` as applicable. Acceptance shall contain `run-acceptance-tests.bat`, required test and instrumentation files and machine-readable traceability, but no compiled production traceability workbook or human-readable test/diagnostic reports. Production shall contain `run-virtual-admin.bat` and application files, exclude the acceptance launcher and `tests/` directory, and contain the production reports defined in FR-016. Validate edition contents and package layout before checksumming.
- **FR-016 [Implemented; verification pending]** Generate `info/release.pdf` for the production ZIP only, from Git commit summaries since the preceding application version, identifying current and preceding versions and release source commit. For an initial baseline without preceding application-version history, identify current version and source commit and explicitly state that earlier release history is absent; never invent historical evidence. Production shall also include `info/traceability.xlsx`, `info/test-results.pdf`, `info/test-evidence.pdf` and `info/test-coverage.pdf`, generated from verified traceability, acceptance and coverage evidence. Verify production report contents, provenance and SHA-256 manifest entries before approval and publication. Acceptance ZIPs shall exclude these production-only reports.
 
## 4. Project-specific controlled document requirements

FR-012 defines the application-specific formatting configuration and its PDF report. Both are inventoried in `app-repo:docs/document-register.json`.

| Document path | Governing FR | Purpose | Required status |
|---|---|---|---|
| `app-repo:config/format-checks.json` | FR-012 | Machine-readable formatting checks | required |
| `info/formatting-checks.pdf` | FR-012 | Human-readable mirror of formatting configuration | required |

## 5. Acceptance test matrix
| Test ID | Requirement IDs | Scenario / expected outcome | Results document |
|---|---|---|---|
| AT-001 | FR-001, FR-007 | Run Word COM and comparison engine | Read uploaded JSON in `tests/results/` |
| AT-002 | FR-004 | Word with incorrect font family, size, bold or italic in target; word highlighted in `<original filename>-HIGHLIGHT.docx` | Read uploaded JSON in `tests/results/` |
| AT-003 | FR-006 | Inputs unchanged; existing `<original filename>-HIGHLIGHT.docx` or `activity.docx` is not overwritten | Read uploaded JSON in `tests/results/` |
| AT-004 | FR-005 | Successful comparison creates `activity.docx` with a summary table first (timings, paragraphs, findings/errors), then Errors and Summary of changes last; no TXT generated | Read uploaded JSON in `tests/results/` |
| AT-005 | FR-009 | Different text/paragraph counts reported | Read uploaded JSON in `tests/results/` |
| AT-006 | FR-002, FR-003, FR-010 | Missing template or target causes nonzero exit and error | Read uploaded JSON in `tests/results/` |
| AT-007 | FR-002, FR-003 | Launcher selects first alphabetically sorted `.dotx` and `.docx` files from its directory | Read uploaded JSON in `tests/results/` |
| AT-008 | FR-011 | Inject a formatting property-read failure after a detectable difference; `activity.docx` retains partial findings under Summary of changes and records failed check details under Errors; exits unsuccessfully and leaves inputs unchanged | Read uploaded JSON in `tests/results/` |
| AT-010 | FR-012 | Compare every check in the generated PDF report with JSON, including disabled checks and Enabled Y/blank mapping, and verify release version; deliberately alter a check description and confirm mismatch rejection | Read uploaded JSON in `tests/results/` |
| AT-011 | FR-012, FR-015 | Check the extracted acceptance package contains the PDF report, required files and only batch launchers at its root; the release packaging scripts additionally validate ZIP contents before checksumming | Read uploaded JSON in `tests/results/` |

| AT-012 [Pending] | FR-013, FR-014 | Verify supported Windows syntax/runtime, acceptance JSON provenance, measured execution and diagnostic separation | Read uploaded JSON in `tests/results/` |
| AT-013 [Pending] | FR-015, FR-016 | Verify acceptance/production ZIP contents, initial-baseline release report, production-only reports and manifest hashes | Read release verification evidence |

## 6. Installation and upgrade
Download or clone repository, install desktop Microsoft Word, and double-click run-virtual-admin.bat in an interactive Windows desktop session. By default, the launcher selects the first `.dotx` and first `.docx` file in alphabetical filename order alongside it. PowerShell script accepts alternative paths. Upgrades replace scripts while retaining documents and reports. FR-006 archives existing outputs on subsequent runs.

## 7. Windows acceptance testing

Tests requiring Word automation run on an interactive Windows desktop with Microsoft Word installed. Application-specific Windows execution and evidence formats are defined in FR-013–FR-016; common verification and provenance controls are governed by the Development Standards R03–R08.

## 8. Known limitations and outstanding work
Structural comparisons may use positional alignment; CHAR-001 formatting checks use named template styles regardless of paragraph position. It does not fully compare tables, headers, footers, fields, themes, section-level layout, track changes or list numbering. Text changes are highlighted at paragraph level. The sole enabled CHAR-001 font family, size, bold and italic properties are defined in `app-repo:config/format-checks.json`. Configuration validation and unsupported-check errors are written to the Errors section of `activity.docx` beside the target document; ordinary findings appear in its Summary of changes. Word may normalize font properties. Formatting changes within different text lengths cannot be aligned reliably.

## 9. Release variants and production approval

**Reserved Release stages:** **Acceptance** produces a prerelease distribution for interactive acceptance testing and does not authorize production use. **Production** produces the approved distribution only after mandatory evidence, provenance and approval gates pass. These names refer to stages, not the activity of acceptance testing.

Application-specific release editions, packaging and reporting are defined in FR-015–FR-016; common evidence integrity, approval and publication controls are governed by the Development Standards R05–R08 and implemented through `.github/workflows/release.yml`.

## 10. Change history
| Version | Date | Summary |
|---|---|---|
| v3.48 | 2026-11-06 | Make the Functional Specification authoritative for Windows packaging, testing and reporting; transfer requirements from central Development Standards and add pending verification mappings. |
| v3.47 | 2026-11-05 | Clarify style comparison, upgrade archiving and release evidence provenance. |
| v3.46 | 2026-11-05 | Remove duplicated Development Standards governance and simplify scope, controlled documents, acceptance and release sections; correct FR-012 version authority. |
| v3.45 | 2026-11-05 | Remove redundant release.pdf example from general Development Standards R08 cross-reference. |
| v3.44 | 2026-11-05 | Align with Development Standards R08: release.pdf is bundled in production only, not acceptance. |
| v3.43 | 2026-11-05 | Retire FR-013 as a functional requirement; Development Standards R08 governs release reports and packaging. Retain AT-011 packaging checks under release governance and FR-012 PDF verification. |
| v3.42 | 2026-11-05 | Remove duplicated document revision date from header; use change history as authority. |
| v3.41 | 2026-11-05 | Replace duplicated current application and governing-standard versions with authoritative references. |
| v3.40 | 2026-11-05 | Standardize document version history and governing Development Standards v7.27 reference; application version displayed with v prefix. |
| 0.2.8 (document revision 3.7) | 2026-11-04 | Synchronize governing Development Standards v5.16 and controlled test-results references; no application behaviour change |
| 0.2.8 (document revision 3.6) | 2026-11-04 | Permit absent pre-acceptance evidence in controlled register; require release.pdf and preserve production evidence gating |
| 0.2.8 (document revision 3.5) | 2026-11-04 | Generate release.pdf from Git changes since preceding application version and require it in both release editions |
| 0.2.8 (document revision 3.4) | 2026-11-04 | PDF register lists all JSON checks, including disabled/planned, with Enabled Y/blank column; retains left-aligned title and white header text |
| 0.2.8 (document revision 3.3) | 2026-11-04 | Retire redundant Excel workbook and its rebuild workflow; retain JSON-authoritative generated PDF register and add tabulated Development Standards workflow implementation index |
| 0.2.8 (document revision 3.2) | 2026-11-04 | Restrict tests/results to current release evidence, preserve historical summaries and Git history; no application behaviour change |
| 0.2.8 (document revision 3.1) | 2026-11-04 | Add automatic fail-closed pre-release validation for syntax, regression, documentation and evidence; application comparison behaviour unchanged; fresh desktop acceptance required |
| 0.2.7 (document revision 3.0) | 2026-11-04 | Increment release candidate to v0.2.7 without application behaviour changes; v0.2.6 acceptance evidence retained historically; new version-matched verification required |
| 0.2.6 (document revision 2.9) | 2026-11-04 | Activity report summary table and full-paragraph highlighted changes without character-by-character listings; fresh acceptance verification required |
| 0.2.4 (document revision 2.4) | 2026-11-04 | Start new acceptance candidate for comparison progress and Esc cancellation; existing v0.2.3 release retained and v0.2.4 acceptance pending |
| 0.2.3 (document revision 2.1) | 2026-11-04 | Update governing Development Standards to v5.10; clarify synchronization-before-verification ordering |
| 0.2.3 (document revision 2.0) | 2026-11-04 | Reference concise Development Standards v5.9; application behaviour unchanged |
| 0.2.3 (document revision 1.9) | 2026-11-04 | Update governing Development Standards reference to v5.8; no application version change |
| 0.2.3 (document revision 1.8) | 2026-11-04 | Implement PDF report generator, package validation and acceptance checks; acceptance evidence pending |
| 0.2.3 (document revision 1.7) | 2026-11-04 | Amend FR-012/FR-013 target from XLSX to version-titled PDF; implementation and acceptance verification pending; application version unchanged |
| 0.2.3 (document revision 1.4) | 2026-11-04 | Clarify release-candidate version timing and specification authority under Development Standards v5.4; no application release bump for documentation-only change |
| 0.2.3 (document revision 1.3) | 2026-11-04 | Make the specification application version authoritative for release version; maintain 0.2.3 for documentation-only change |
| 0.2.3 (document revision 1.2) | 2026-11-04 | Clarify release SemVer governed by Development Standards v5.2; retain application version 0.2.3 for documentation-only change |
| 0.2.3 (document revision 1.1) | 2026-11-04 | Introduce independent controlled document revisions and align governing Development Standards reference to v5.1 |
| 0.2.3 (FR-013 development) | 2026-11-03 | Include Excel format-check register in acceptance and production ZIPs; relocate other non-batch files under `config/`, `src/`, `docs/` and `tests/`, retaining PDF at the ZIP root at that historical revision; add ZIP validation and AT-011 |
| 0.2.3 (FR-012 development) | 2026-11-03 | Add PDF formatting-check report under `config/`, create automated JSON/Excel alignment verification and map new AT-010; AT-009 remains retired |
| 0.2.3 (FR-011 revision, unverified) | 2026-11-03 | Replace configuration-schema functional requirement with comparison-execution failure reporting; reassign AT-008, delete AT-009; retain disabled planned checks in implementation configuration |
| 0.2.3 (development) | 2026-11-03 | Add JSON-driven character, paragraph and page-layout checks; generate Errors.docx for missing, invalid or unsupported checks; update the Development Standards pin to v4.18 and expand the Windows PowerShell script coverage requirement |
| 0.2.3 | 2026-11-03 | Embed version and exact source commit in `virtual-admin-build.json`; acceptance evidence reads and records package provenance; production approval requires exact source-commit match |
| 0.1.0 | 2026-11-03 | Initial Windows Word comparison proof of concept |
| 0.2.0 | 2026-11-03 | Require fixed local DOTX/DOCX filenames, explicit launcher errors, and manual gated release design |

### Requirement renumbering history (approved 2026-11-03)
Removed former FR-006 (paragraph formatting), FR-005 (page setup), FR-007 (highlight output as a separate requirement). Highlighting remains part of FR-004. Renumbered former FR-008→FR-006, FR-009→FR-005, FR-002→FR-007, FR-003→FR-008, FR-010→FR-009, in accordance with master standard v4.6 Rule 3.04. Former AT-003 and AT-004 removed; former AT-005→AT-003, AT-006→AT-004, AT-007→AT-005.
