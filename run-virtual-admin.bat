@echo off
rem FR-007, FR-002, FR-003, FR-010: Select local inputs and launch the interactive comparison.
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
rem FR-006: Archive previous output files before selecting the input DOCX.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0src\archive-previous-outputs.ps1" -LauncherDirectory "%~dp0"
if errorlevel 1 (
  echo ERROR: Could not archive previous output documents. Comparison cancelled.
  exit /b 1
)
set "template="
set "document="
for /f "delims=" %%F in ('dir /b /a-d /on "%~dp0*.dotx" 2^>nul') do if not defined template set "template=%~dp0%%F"
for /f "delims=" %%F in ('dir /b /a-d /on "%~dp0*.docx" 2^>nul') do if not defined document set "document=%~dp0%%F"
if not defined template (
  echo ERROR: No .dotx approved template found beside this batch file.
  exit /b 2
)
if not defined document (
  echo ERROR: No .docx document to check found beside this batch file.
  exit /b 2
)
echo Approved template: "%template%"
echo Document to check: "%document%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0src\compare-formatting.ps1" -TemplatePath "%template%" -DocumentPath "%document%"
if errorlevel 1 (
  echo ERROR: Document comparison failed.
  exit /b 1
)
exit /b 0
