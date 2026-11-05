# DevStan R08: Validate release ZIP contents, register inclusion and permitted root layout.
# DevStan R08: Verify the release ZIP contains the required application files and layout.
param(
 [Parameter(Mandatory=$true)][string]$ArchivePath,
 [Parameter(Mandatory=$true)][ValidateSet('acceptance','production')][string]$Edition
)
$ErrorActionPreference='Stop'
try {
 if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {throw "Archive missing: $ArchivePath"}
 Add-Type -AssemblyName System.IO.Compression
 Add-Type -AssemblyName System.IO.Compression.FileSystem
 $archive=[System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ArchivePath).Path)
 try {
  $paths=@($archive.Entries | ForEach-Object { $_.FullName.Replace([char]92,[char]47) } | Where-Object { -not $_.EndsWith('/') })
  $seen=@{}
  foreach($entryPath in $paths) {
   if($seen.ContainsKey($entryPath)){throw "Duplicate archive entry: $entryPath"}
   $seen[$entryPath]=$true
   if(-not $entryPath.Contains('/') -and $entryPath -notmatch '\.bat$') {
    throw "Unexpected ZIP root file: $entryPath"
   }
  }
  if(@($paths | Where-Object { $_ -ceq 'info/formatting-checks.pdf' }).Count -ne 1) {
   throw 'Expected exactly one PDF register in info/'
  }
  if($Edition -eq 'production' -and @($paths | Where-Object { $_ -ceq 'info/release.pdf' }).Count -ne 1) {throw 'Expected exactly one release.pdf in production info/'}
  if($Edition -eq 'acceptance' -and @($paths | Where-Object { $_ -ceq 'info/release.pdf' }).Count -ne 0) {throw 'Acceptance ZIP must not contain release.pdf'}
  $required=@('run-virtual-admin.bat','src/compare-formatting.ps1','src/archive-previous-outputs.ps1','config/format-checks.json','info/formatting-checks.pdf','config/virtual-admin-build.json')
  if($Edition -eq 'production') { $required+=@('info/release.pdf','info/traceability.xlsx','info/test-results.pdf','info/test-evidence.pdf','info/test-coverage.pdf') }
  if($Edition -eq 'acceptance') {
   $required+=@('run-acceptance-tests.bat','docs/README.md','docs/installation.md','docs/functional-specification.md','docs/AGENTS.md','docs/traceability.json','tests/test-functional-acceptance.ps1','tests/measure-code-coverage.ps1','tests/compile-code-coverage.ps1','tests/test-format-checks-alignment.ps1')
  }
  if($Edition -eq 'acceptance' -and @($paths | Where-Object { $_ -in @('info/traceability.xlsx','info/test-results.pdf','info/test-evidence.pdf','info/test-coverage.pdf') }).Count -gt 0) { throw 'Acceptance ZIP contains production-only traceability or test evidence' }
  foreach($name in $required) {if(-not $seen.ContainsKey($name)){throw "Required archive entry missing: $name"}}
  if($Edition -eq 'production' -and @($paths | Where-Object { $_ -match '^tests/' -or $_ -eq 'run-acceptance-tests.bat' }).Count -gt 0) {
   throw 'Production ZIP contains acceptance-testing files'
  }
  Write-Host "PASS: $Edition ZIP has correct edition-specific documents and required subdirectories."
 } finally {$archive.Dispose()}
} catch {
 Write-Error "ZIP layout verification failed: $($_.Exception.Message)"
 exit 1
}
# Explicitly reset the script exit status; callers rely on LASTEXITCODE,
# which otherwise may retain a prior native command's nonzero exit code.
exit 0
