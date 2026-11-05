@echo off
rem FR-002, FR-004, FR-011, FR-012, FR-013: Launch mapped Windows acceptance tests.
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tests\test-functional-acceptance.ps1"
set "result=%errorlevel%"
echo.
if "%result%"=="0" (echo All automated tests passed.) else (echo Tests failed or blocked. See tests\results.)
pause
exit /b %result%
