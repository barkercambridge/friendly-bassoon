# FR-013: Summarise measured coverage of the extracted acceptance release.
param(
 [Parameter(Mandatory=$true)][string]$PackageRoot,
 [Parameter(Mandatory=$true)][string]$ResultsDirectory,
 [Parameter(Mandatory=$true)][string]$CoverageDirectory,
 [Parameter(Mandatory=$true)][string]$Version,
 [Parameter(Mandatory=$true)][string]$AcceptanceZipSha256,
 [Parameter(Mandatory=$true)][string]$SourceCommit
)
$ErrorActionPreference='Stop'
$files=@('src/compare-formatting.ps1','src/archive-previous-outputs.ps1','run-virtual-admin.bat')
$records=@()
foreach($relative in $files){
 $path=Join-Path $PackageRoot $relative
 $hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
 if($relative.EndsWith('.ps1')){
  $tokens=$null;$parseErrors=$null
  $ast=[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$parseErrors)
  if(@($parseErrors).Count -gt 0){throw "Coverage parsing failed: $relative"}
  $executable=@($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.StatementAst]},$true) |
    ForEach-Object {$_.Extent.StartLineNumber} | Sort-Object -Unique)
  $observed=@()
  $hitFiles=@()
  $invalidHits=@()
  if($relative -in @('src/compare-formatting.ps1','src/archive-previous-outputs.ps1')){
   foreach($file in @(Get-ChildItem -LiteralPath $CoverageDirectory -Filter $(if($relative -eq 'src/compare-formatting.ps1'){'engine-*.hits'}else{'archive-*.hits'}) -File -ErrorAction SilentlyContinue)){
    $hitFiles += $file.Name
    foreach($entry in @(Get-Content -LiteralPath $file.FullName)){
     if($entry -match '^\d+$'){$observed += [int]$entry}
     elseif(-not [string]::IsNullOrWhiteSpace($entry)){$invalidHits += $entry}
    }
   }
  }
  $reason=if($hitFiles.Count -eq 0){'No coverage hit files were created'}elseif($invalidHits.Count -gt 0){'Coverage hit files contain nonnumeric entries'}elseif($observed.Count -eq 0){'Coverage hit files contain no recorded lines'}else{$null}
  $hit=@($executable | Where-Object {$_ -in $observed})
  $miss=@($executable | Where-Object {$_ -notin $observed})
  $records+=@{path=$relative;sha256=$hash;diagnostic_reason=$reason;hit_file_count=$hitFiles.Count;invalid_hit_count=$invalidHits.Count;measurement=$(if($relative -in @('src/compare-formatting.ps1','src/archive-previous-outputs.ps1') -and $observed.Count -gt 0 -and $invalidHits.Count -eq 0){'MEASURED'}else{'NOT MEASURED'});executable_lines=@($executable);covered_lines=@($hit);uncovered_lines=@($miss);coverage_percentage=$(if($executable.Count -gt 0){[math]::Round(100.0*$hit.Count/$executable.Count,2)}else{$null});excluded=$false}
 } else {
  $records+=@{path=$relative;sha256=$hash;measurement='NOT MEASURED';reason='Batch launcher execution coverage instrumentation not available';executable_lines=@();covered_lines=@();uncovered_lines=@();coverage_percentage=$null;excluded=$true}
 }
}
$metadataPath=Join-Path $PackageRoot 'config/virtual-admin-build.json'
$metadata=Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
if (-not $metadata.release_input_fingerprint -or ([string]$metadata.release_input_fingerprint).Length -ne 64) { throw 'Release-input fingerprint missing from package metadata' }
$report=[ordered]@{
 schema_version=1;application='virtual-admin';version=$Version;source_commit=$SourceCommit;release_input_fingerprint=$metadata.release_input_fingerprint;acceptance_zip_sha256=$AcceptanceZipSha256
 timestamp_utc=(Get-Date).ToUniversalTime().ToString('o')
 coverage_method='PowerShell statement-line breakpoints in released comparison engine and archive helper; batch launcher unmeasured'
 exclusions=@($records | Where-Object {$_.excluded} | ForEach-Object {@{path=$_.path;reason=$_.reason}})
 files=@($records)
}
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $ResultsDirectory 'code-coverage.json') -Encoding UTF8
$diagnostics=[ordered]@{timestamp_utc=(Get-Date).ToUniversalTime().ToString('o');source_commit=$SourceCommit;status=$(if(@($records | Where-Object {-not $_.excluded -and $_.measurement -ne 'MEASURED'}).Count -eq 0){'PASS'}else{'FAIL'});files=@($records | Where-Object {-not $_.excluded} | ForEach-Object {@{path=$_.path;measurement=$_.measurement;reason=$_.diagnostic_reason;hit_file_count=$_.hit_file_count;invalid_hit_count=$_.invalid_hit_count}})}
$diagnostics | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ResultsDirectory 'coverage-diagnostics.json') -Encoding UTF8
Write-Host "Coverage: $(@($records | Where-Object {$_.measurement -eq 'MEASURED'}).Count) measured files; $(@($records | Where-Object {$_.measurement -ne 'MEASURED'}).Count) unmeasured files."
