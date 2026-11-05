# DevStan R08: Build and validate acceptance/production ZIP layout and required register files.
[CmdletBinding()]
# DevStan R08: Validate and package the acceptance distribution with required files.
param(
    [ValidatePattern('^\d+\.\d+$')]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Commit,
    [ValidateSet('acceptance', 'production')]
    [string]$Edition = 'acceptance'
)

$ErrorActionPreference = 'Stop'

# FR-012 / R04: traceability.json is the sole authoritative release version.
$traceabilityPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'traceability.json'
if (-not (Test-Path -LiteralPath $traceabilityPath -PathType Leaf)) {
    throw 'Authoritative traceability.json is missing.'
}
$authoritativeVersion = [string]((Get-Content -LiteralPath $traceabilityPath -Raw | ConvertFrom-Json).version)
if ($authoritativeVersion -cnotmatch '^(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)$') {
    throw 'Invalid application version in traceability.json.'
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = $authoritativeVersion
}
elseif ($Version -cne $authoritativeVersion) {
    throw "Package version $Version does not match authoritative traceability.json version $authoritativeVersion."
}

$checkedOutCommit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $checkedOutCommit -cne $Commit) {
    throw 'Package source commit does not match the checked-out Git commit.'
}

$commonFiles = @(
    'src/compare-formatting.ps1','src/archive-previous-outputs.ps1',
    'config/format-checks.json',
    'info/formatting-checks.pdf',
    'README.md',
    'docs/installation.md',
    'docs/functional-specification.md',
    'AGENTS.md'
)
if ($Edition -eq 'acceptance') {
    $files = $commonFiles + @(
        'run-virtual-admin.bat',
        'tests/run-acceptance-tests.bat',
        'tests/test-functional-acceptance.ps1',
        'tests/measure-code-coverage.ps1',
        'tests/compile-code-coverage.ps1',
        'tests/test-format-checks-alignment.ps1',
        'traceability.json'
    )
}
else {
    $files = $commonFiles + @('run-virtual-admin.bat', 'info/release.pdf', 'info/traceability.xlsx', 'info/test-results.pdf', 'info/test-evidence.pdf', 'info/test-coverage.pdf')
}

# A release is invalid when the report is missing or differs from JSON.
& (Join-Path $PSScriptRoot '..\\tests\\test-format-checks-alignment.ps1') -Version $Version
if ($LASTEXITCODE -ne 0) { throw 'FR-012: text formatting check register differs from JSON.' }

$stage = Join-Path $env:TEMP ('virtual-admin-package-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $stage | Out-Null

try {
    foreach ($file in $files) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Missing package file: $file"
        }
        # Only Windows batch files are allowed at the ZIP root.
        $destinationPath = switch ($file) {
            'README.md' { 'docs/README.md' }
            'AGENTS.md' { 'docs/AGENTS.md' }
            'traceability.json' { 'docs/traceability.json' }
            'tests/run-acceptance-tests.bat' { 'run-acceptance-tests.bat' }
            default { $file }
        }
        $destination = Join-Path $stage $destinationPath
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        Copy-Item -LiteralPath $file -Destination $destination
        if ($file -eq 'README.md') {
            $readme = Get-Content -LiteralPath $destination -Raw
            $readme = $readme.Replace('(docs/installation.md)', '(installation.md)').Replace('(docs/functional-specification.md)', '(functional-specification.md)').Replace('(AGENTS.md)', '(AGENTS.md)')
            Set-Content -LiteralPath $destination -Value $readme -Encoding UTF8
        }
    }

    $releaseInputFingerprint = (& python scripts/acceptance-evidence-freshness.py --print-fingerprint $Commit | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $releaseInputFingerprint.Length -ne 64) { throw 'Cannot calculate release-input fingerprint' }
    $metadata = [ordered]@{
        application = 'virtual-admin'
        version = $Version
        source_commit = $Commit
        release_input_fingerprint = $releaseInputFingerprint
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'config/virtual-admin-build.json') -Encoding UTF8

    New-Item -ItemType Directory -Force -Path 'dist' | Out-Null
    $zipName = "virtual-admin-$Edition-v$Version.zip"
    $checksumName = "virtual-admin-$Edition-v$Version.sha256"
    $zipPath = Join-Path (Resolve-Path 'dist').Path $zipName
    $checksumPath = Join-Path (Resolve-Path 'dist').Path $checksumName
    if ((Test-Path -LiteralPath $zipPath) -or (Test-Path -LiteralPath $checksumPath)) {
        throw "Refusing to overwrite existing package output for $Edition v$Version."
    }

    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath
    & (Join-Path $PSScriptRoot '../tests/test-package-archive.ps1') -ArchivePath $zipPath -Edition $Edition
    if ($LASTEXITCODE -ne 0) { throw 'Release archive layout verification failed.' }
    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $checksumPath -Value "$hash  $zipName" -Encoding ASCII
    Write-Host "Package: $zipPath"
    Write-Host "SHA256: $checksumPath"
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
