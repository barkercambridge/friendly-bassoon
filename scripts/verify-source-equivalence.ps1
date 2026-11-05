[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$TestedCommit,
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ReleaseCommit,
 [string]$EvidenceDir='release-evidence'
)
$ErrorActionPreference='Stop'
# Only controlled acceptance-results.json and code-coverage.json uploads is exempt from retesting.
# Only explicitly listed editorial documentation may also change without retesting.
$policyPath=Join-Path $PSScriptRoot '../config/release-input-exemptions.json'
$policy=Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json
$allowed=@($policy.evidence_paths)
$editorial=@($policy.editorial_paths)
if (@($allowed).Count -ne 2 -or 'tests/results/acceptance-results.json' -notin $allowed -or 'tests/results/code-coverage.json' -notin $allowed) { throw 'Invalid evidence exemption policy' }
function Is-Administrative([string]$Path) {
 if($Path -in $allowed -or $Path -in $editorial){return $true}
 return $false
}
& git cat-file -e ($TestedCommit+'^{commit}')
if($LASTEXITCODE -ne 0){throw 'Tested commit is unavailable'}
& git cat-file -e ($ReleaseCommit+'^{commit}')
if($LASTEXITCODE -ne 0){throw 'Release commit is unavailable'}
& git merge-base --is-ancestor $TestedCommit $ReleaseCommit
if($LASTEXITCODE -ne 0){throw 'Tested commit must be an ancestor of release commit'}
$changes=@(& git diff --no-renames --name-only $TestedCommit $ReleaseCommit --)
if($LASTEXITCODE -ne 0){throw 'Git comparison failed'}
$records=@()
$invalid=@()
foreach($path in $changes){
 if([string]::IsNullOrWhiteSpace($path)){continue}
 $administrative=Is-Administrative $path
 $testedEntry=(& git ls-tree $TestedCommit -- $path | Out-String).Trim()
 if($LASTEXITCODE -ne 0){throw "Failed to inspect tested path: $path"}
 $releaseEntry=(& git ls-tree $ReleaseCommit -- $path | Out-String).Trim()
 if($LASTEXITCODE -ne 0){throw "Failed to inspect release path: $path"}
 $testedHash=$null
 $releaseHash=$null
 if($testedEntry -match '^[0-9]{6}\s+blob\s+([0-9a-f]{40})\s+'){$testedHash=$Matches[1]}
 if($releaseEntry -match '^[0-9]{6}\s+blob\s+([0-9a-f]{40})\s+'){$releaseHash=$Matches[1]}
 if($testedEntry -and -not $testedHash){throw "Unrecognised tested tree entry: $path"}
 if($releaseEntry -and -not $releaseHash){throw "Unrecognised release tree entry: $path"}
 $records+=@{path=$path;tested_blob=$testedHash;release_blob=$releaseHash;administrative=$administrative}
 if(-not $administrative){$invalid+=$path}
}
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$report=@{tested_commit=$TestedCommit;release_commit=$ReleaseCommit;timestamp_utc=(Get-Date).ToUniversalTime().ToString('o');method='git diff --no-renames plus immutable Git blobs; all non-administrative changes rejected';changed_paths=$records;release_affecting_changes=$invalid;equivalent=($invalid.Count -eq 0)}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $EvidenceDir 'source-equivalence.json') -Encoding UTF8
if($invalid.Count -gt 0){throw "Acceptance retest required: release-affecting changes: $($invalid -join ', ')"}
Write-Host "Source-equivalence verified: $TestedCommit -> $ReleaseCommit"
