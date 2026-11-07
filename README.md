# Word formatting checker

Compare a Word document against an approved Word template on a Windows desktop. The application creates a highlighted copy showing formatting differences and an `activity.docx` report.

## Prerequisites

- Windows with desktop Microsoft Word installed and opened at least once under your user account. Word Online is not supported.
- Windows PowerShell 5.1.
- A `.dotx` template and a `.docx` document to check.
- Normal user permissions; administrator access is not required.

## Install and quick start

1. Download or extract the application files, keeping their folder structure intact.
2. Place the approved `.dotx` template and target `.docx` document beside `run-virtual-admin.bat`.
3. Double-click `run-virtual-admin.bat`.
4. Open `<document name>-HIGHLIGHT.docx` and `activity.docx` beside the checked document to review the results.

The launcher selects the first filename in alphabetical order for each required extension. If either input is missing, it displays an error and exits without running the comparison. On subsequent runs, previous highlighted documents and `activity.docx` are moved to the `old` folder with timestamped names. If archiving fails, the comparison stops.

If Windows blocks a downloaded script, check **Properties → Unblock** and run only files from a trusted source. The launcher invokes PowerShell for that run without changing the machine-wide execution policy.

## Use custom document paths

From the application directory, run:

```powershell
powershell.exe -NoProfile -File .\src\compare-formatting.ps1 -TemplatePath 'C:\path\template.dotx' -DocumentPath 'C:\path\target.docx'
```

The comparison engine reads `config/format-checks.json`. Configuration or execution errors are reported in `activity.docx` next to the checked document.

## Upgrade and removal

To upgrade, replace the application scripts while preserving your input documents and existing output files. Keep the application folder structure intact.

To remove the application, delete its scripts and supporting application files. There is no installed background service. Input documents, archived files and generated reports remain until you choose to remove them.
