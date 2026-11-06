# FR-013: Validate the single authoritative acceptance JSON before production.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$Version,
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Commit
)
$ErrorActionPreference='Stop'
$rtm=Get-Content -LiteralPath 'config/traceability.json' -Raw | ConvertFrom-Json
if($rtm.version -ne $Version){throw 'Production blocked: traceability version mismatch'}
$path='tests/results/acceptance-results.json'
if(-not (Test-Path -LiteralPath $path -PathType Leaf)){throw 'Production blocked: acceptance JSON missing'}
$other=@(Get-ChildItem -LiteralPath 'tests/results' -Force | Where-Object { $_.Name -notin @('acceptance-results.json','code-coverage.json','coverage-diagnostics.json') })
if($other.Count -ne 0){throw 'Production blocked: additional acceptance results found'}
$e=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
$required=@($rtm.acceptance_tests | Where-Object { $_.stage -eq 'Acceptance' -and $_.status -eq 'required' } | ForEach-Object { $_.id })
if($e.version -ne $Version -or $e.application -ne 'virtual-admin' -or $e.source_commit -cnotmatch '^[0-9a-f]{40}$'){throw 'Production blocked: invalid evidence provenance'}
if($e.passed -ne $required.Count -or $e.failed -ne 0 -or $e.blocked -ne 0 -or @($e.tests).Count -ne $required.Count){throw 'Production blocked: acceptance results incomplete'}
foreach($id in $required){
 $records=@($e.tests | Where-Object {$_.test_id -eq $id})
 if($records.Count -ne 1 -or $records[0].status -ne 'PASS'){throw "Production blocked: expected one PASS for $id"}
}
$diagnosticsPath='tests/results/coverage-diagnostics.json'
if(-not (Test-Path -LiteralPath $diagnosticsPath -PathType Leaf)){throw 'Production blocked: diagnostics missing'}
$d=Get-Content -LiteralPath $diagnosticsPath -Raw | ConvertFrom-Json
if($d.status -ne 'PASS' -or $d.source_commit -cne $e.source_commit){throw 'Production blocked: diagnostics provenance mismatch'}
$expectedDiagnostics=@('src/compare-formatting.ps1','src/archive-previous-outputs.ps1')
if(@($d.files).Count -ne $expectedDiagnostics.Count){throw 'Production blocked: diagnostics inventory mismatch'}
foreach($name in $expectedDiagnostics){
 $entries=@($d.files | Where-Object { $_.path -ceq $name })
 if($entries.Count -ne 1 -or $entries[0].measurement -ne 'MEASURED' -or $entries[0].invalid_hit_count -ne 0 -or $entries[0].hit_file_count -lt 1){throw "Production blocked: invalid diagnostics for $name"}
}
$coveragePath='tests/results/code-coverage.json'
if(-not (Test-Path -LiteralPath $coveragePath -PathType Leaf)){throw 'Production blocked: code coverage JSON missing'}
$c=Get-Content -LiteralPath $coveragePath -Raw | ConvertFrom-Json
if($c.release_input_fingerprint -cne $e.release_input_fingerprint -or $c.schema_version -ne 1 -or $c.application -ne 'virtual-admin' -or $c.version -ne $Version -or $c.source_commit -cne $e.source_commit){throw 'Production blocked: coverage provenance mismatch'}
if($e.acceptance_zip_sha256 -notmatch '^[0-9a-f]{64}$' -or $c.acceptance_zip_sha256 -cne $e.acceptance_zip_sha256){throw 'Production blocked: acceptance ZIP SHA-256 missing or inconsistent between evidence files'}
$expected=@('src/compare-formatting.ps1','src/archive-previous-outputs.ps1','run-virtual-admin.bat')
if(@($c.files).Count -ne $expected.Count){throw 'Production blocked: incomplete code coverage inventory'}
foreach($name in $expected){
 $entries=@($c.files | Where-Object {$_.path -ceq $name})
 if($entries.Count -ne 1){throw "Production blocked: missing or duplicate coverage file $name"}
 $actual=(Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash.ToLowerInvariant()
 if($entries[0].sha256 -cne $actual){throw "Production blocked: coverage source hash differs for $name"}
}
$engine=@($c.files | Where-Object {$_.path -ceq 'src/compare-formatting.ps1'})[0]
if($engine.measurement -ne 'MEASURED' -or @($engine.covered_lines).Count -eq 0){throw 'Production blocked: comparison engine coverage not measured'}
$archive=@($c.files | Where-Object {$_.path -ceq 'src/archive-previous-outputs.ps1'})[0]
if($archive.measurement -ne 'MEASURED' -or @($archive.covered_lines).Count -eq 0){throw 'Production blocked: archival helper coverage not measured'}
& (Join-Path $PSScriptRoot 'verify-source-equivalence.ps1') -TestedCommit $e.source_commit -ReleaseCommit $Commit
if($LASTEXITCODE -ne 0){throw 'Production blocked: source equivalence failed'}
Write-Host "Current acceptance JSON verified for $Version; tested commit $($e.source_commit)"
