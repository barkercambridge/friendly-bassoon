# FR-006: Archive previous outputs before the launcher selects the next input.
param([Parameter(Mandatory=$true)][string]$LauncherDirectory)
$ErrorActionPreference = 'Stop'
$directory = (Resolve-Path -LiteralPath $LauncherDirectory -ErrorAction Stop).Path
$oldDirectory = Join-Path $directory 'old'
$previous = @(Get-ChildItem -LiteralPath $directory -File | Where-Object {
    $_.Name -ieq 'activity.docx' -or $_.Name -imatch '-HIGHLIGHT(?:ED)?[.]docx$'
})
if ($previous.Count -eq 0) { return }
if (-not (Test-Path -LiteralPath $oldDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $oldDirectory -Force -ErrorAction Stop | Out-Null
}
foreach ($file in $previous) {
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stem = [IO.Path]::GetFileNameWithoutExtension($file.Name)
    $extension = $file.Extension
    $counter = 0
    do {
        $suffix = if ($counter -eq 0) { '' } else { '-' + $counter }
        $destination = Join-Path $oldDirectory ($stem + '-' + $timestamp + $suffix + $extension)
        $counter++
    } while (Test-Path -LiteralPath $destination)
    Move-Item -LiteralPath $file.FullName -Destination $destination -ErrorAction Stop
    Write-Host ('Archived: {0} -> {1}' -f $file.Name, (Split-Path -Leaf $destination))
}
