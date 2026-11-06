# Windows proof-of-concept installation

1. Install desktop Microsoft Word and open it once under your Windows user account.
2. Download the repository files, retaining the folder structure.
3. Put your approved `.dotx` template and target `.docx` document beside `run-virtual-admin.bat`. The batch launcher selects the first filename in alphabetical order for each extension from its own directory; it prints an error and exits with code 2 if either extension is absent. The underlying PowerShell engine can still accept custom paths.
4. Double-click `run-virtual-admin.bat`. No elevation is required.
5. Review the generated `<document name>-HIGHLIGHT.docx` and `activity.docx` next to the input document.
6. On subsequent runs, the launcher automatically moves existing `activity.docx`, `*-HIGHLIGHT.docx` and `*-HIGHLIGHTED.docx` into an `old` subfolder, creating it if necessary. Archived filenames receive a local date-time stamp and collision-safe suffix. If archiving fails, the comparison stops; the engine also refuses to overwrite existing outputs.

The batch launcher uses `powershell.exe -NoProfile -ExecutionPolicy Bypass -File` for this invocation only; it does not change machine-wide policy. Only run scripts you trust. Files downloaded from the internet may require Windows Properties → Unblock. Word desktop COM automation is required; Word Online alone is insufficient.

For a custom comparison:
```powershell
powershell.exe -NoProfile -File .\src\compare-formatting.ps1 -TemplatePath 'C:\path\template.dotx' -DocumentPath 'C:\path\target.docx'
```

Upgrade by replacing scripts. No background service or installation is created. Remove the scripts to uninstall; document files and generated outputs remain in place.


## Format-check specification and errors

The comparison engine reads `app-repo:config/format-checks.json` from the application directory. The file defines only CHAR-001 (font family, size, bold and italic). Do not add other check IDs or change the required scope/property. For each target paragraph, CHAR-001 finds the same named style in the template and compares actual paragraph font family, size, bold and italic with the same properties from that style; it skips per-character inspection only for a definite uniform match of all four properties, otherwise highlights mismatching characters. Paragraph positions and wording do not determine the expected font. The corresponding style must exist in the template. If the specification is missing, invalid, incomplete or contains a check that Word cannot execute, comparison stops and the engine writes `activity.docx` to the same directory as the target document. Open that document to review the configuration or execution errors before retrying.


## Release package folder structure
Both acceptance and production release ZIPs retain only Windows batch launchers at their root; non-test PDF documentation is under `info/`. The Excel `info/traceability.xlsx` workbook and human-readable test reports, including `info/test-coverage.pdf`, are generated and included **only in production**; acceptance includes source-controlled `app-repo:config/traceability.json` mappings without compiled test evidence. The engine is in `src/`; `config/` contains `format-checks.json` and `virtual-admin-build.json`. Documentation is in `docs/`. Acceptance ZIPs contain `run-acceptance-tests.bat` at the ZIP root and the PowerShell test scripts in `tests/`. Double-click the root-level acceptance test launcher on an interactive Windows desktop with Microsoft Word. Production ZIPs contain neither `run-acceptance-tests.bat` nor the `tests/` subfolder.

The PDF register is a human-readable mirror of the sole configured CHAR-001 formatting check. Its check IDs, scope, property, enabled state, status and description must agree with the JSON configuration (FR-012); the packaging process refuses mismatches. Other formatting checks have been removed. The package ZIP is also checked to ensure that non-batch application files other than the PDF register reside in subdirectories (FR-013).

### Activity report

Each comparison writes `activity.docx` beside the checked document. Its opening **Errors** section lists checks or attempted comparisons that could not be completed, with diagnostic details; **None** means no such errors. Its final **Summary of changes** section lists formatting and structural differences. The former `*-differences.txt` and `Errors.docx` outputs are no longer generated. Failed checks cause a nonzero exit; the highlighted copy is a separate output.

Acceptance testing generates `app-repo:tests/results/acceptance-results.json` and `app-repo:tests/results/code-coverage.json` from the extracted acceptance ZIP. Upload both machine-readable files to the repository's `tests/results/` folder. Coverage identifies measured and unmeasured executable code; it does not assert that every line was executed. Release-affecting source changes delete all previous files in `tests/results/` and require new acceptance testing.

## Version history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-11-05 | Establish independently versioned controlled document history. |
