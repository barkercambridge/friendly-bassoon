[CmdletBinding()]
param([string]$EvidenceDir='release-evidence')
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
# Resolve before Push-Location enters the disposable fixture repository.
# Evidence must remain in the caller's release-evidence directory after cleanup.
$EvidenceDir=(Resolve-Path -LiteralPath $EvidenceDir).Path
$verifier=(Resolve-Path (Join-Path $PSScriptRoot '../scripts/verify-source-equivalence.ps1')).Path
$root=Join-Path $env:TEMP ('virtual-admin-git-regression-'+[guid]::NewGuid().ToString('N'))
$results=@()
function Invoke-Git([string[]]$Arguments) {
 $output=& git.exe @Arguments 2>&1
 if($LASTEXITCODE -ne 0){throw "git $($Arguments -join ' ') failed: $output"}
 return $output
}
function Commit([string]$Message){
 Invoke-Git @('add','-A') | Out-Null
 Invoke-Git @('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-m',$Message) | Out-Null
 return ([string](Invoke-Git @('rev-parse','HEAD'))).Trim()
}
try {
 New-Item -ItemType Directory -Force -Path $root | Out-Null
 Push-Location $root
 Invoke-Git @('init','-q') | Out-Null
 New-Item -ItemType Directory -Force -Path 'src' | Out-Null
 Set-Content 'src/app.ps1' 'Write-Host original' -Encoding ASCII
 Set-Content 'README.md' 'documentation' -Encoding ASCII
 [IO.File]::WriteAllBytes((Join-Path $root 'binary.bin'),[byte[]](0,1,2,255))
 $base=Commit 'base'
 $cases=@(
  @{name='unchanged';action={};expected=$true},
  @{name='administrative-doc';action={Set-Content README.md 'new documentation' -Encoding ASCII};expected=$true},
  @{name='devstan-admin-1';action={New-Item -ItemType Directory -Path 'docs' -Force | Out-Null; Set-Content 'docs/document-register.json' 'administrative update' -Encoding ASCII};expected=$false},
  @{name='devstan-admin-2';action={New-Item -ItemType Directory -Path 'scripts' -Force | Out-Null; Set-Content 'scripts/build-traceability.py' 'administrative update' -Encoding ASCII};expected=$false},
  @{name='obsolete-verifier-added';action={New-Item -ItemType Directory -Path 'scripts' -Force | Out-Null; Set-Content 'scripts/verify-devstan-v5.py' 'obsolete verifier reintroduced' -Encoding ASCII};expected=$false},
  @{name='devstan-admin-4';action={New-Item -ItemType Directory -Path 'scripts' -Force | Out-Null; Set-Content 'scripts/verify-devstan.py' 'administrative update' -Encoding ASCII};expected=$false},
  @{name='devstan-admin-5';action={New-Item -ItemType Directory -Path 'tests' -Force | Out-Null; Set-Content 'tests/test-devstan-info-rules.py' 'administrative update' -Encoding ASCII};expected=$false},
  @{name='evidence-only-upload';action={New-Item -ItemType Directory -Path 'tests/results' -Force | Out-Null; Set-Content 'tests/results/acceptance-results.json' '{}' -Encoding ASCII};expected=$true},
  @{name='new-coverage-diagnostics';action={New-Item -ItemType Directory -Path 'tests/results' -Force | Out-Null; Set-Content 'tests/results/coverage-diagnostics.json' '{}' -Encoding ASCII};expected=$true},
  @{name='unexpected-evidence';action={New-Item -ItemType Directory -Path 'tests/results' -Force | Out-Null; Set-Content 'tests/results/extra.json' '{}' -Encoding ASCII};expected=$true},
  @{name='modified-source';action={Set-Content src/app.ps1 'Write-Host modified' -Encoding ASCII};expected=$false},
  @{name='added-source';action={Set-Content src/new.ps1 'new' -Encoding ASCII};expected=$false},
  @{name='deleted-source';action={Remove-Item src/app.ps1};expected=$false},
  @{name='renamed-source';action={Invoke-Git @('mv','src/app.ps1','src/renamed.ps1') | Out-Null};expected=$false},
  @{name='modified-binary';action={[IO.File]::WriteAllBytes((Join-Path $root 'binary.bin'),[byte[]](0,1,3,255))};expected=$false}
 )
 foreach($case in $cases){
  Invoke-Git @('reset','--hard',$base) | Out-Null
  Invoke-Git @('clean','-fd') | Out-Null
  & $case.action
  $candidate=Commit $case.name
  $caseDir=Join-Path $root ('evidence-'+$case.name)
  $success=$false
  $errorText=$null
  try {
   & $verifier -TestedCommit $base -ReleaseCommit $candidate -EvidenceDir $caseDir | Out-Null
   $success=$true
  } catch {$errorText=$_.Exception.Message}
  $pass=($success -eq $case.expected)
  $results+=@{fixture=$case.name;expected_equivalent=$case.expected;actual_equivalent=$success;result=$(if($pass){'PASS'}else{'FAIL'});error=$errorText}
 }
} finally {
 # Always restore the caller's location before deleting the disposable fixture.
 # PowerShell resolves relative paths against its current location, not the script path.
 Pop-Location
 Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
$report=@{application='virtual-admin';test='git-source-equivalence-regression';timestamp_utc=(Get-Date).ToUniversalTime().ToString('o');fixtures=$results;passed=@($results|Where-Object {$_.result -eq 'PASS'}).Count;failed=@($results|Where-Object {$_.result -eq 'FAIL'}).Count}
$report | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDir 'git-equivalence-regression.json') -Encoding UTF8
if($report.failed -gt 0){throw "$($report.failed) Git equivalence regression fixtures failed"}
