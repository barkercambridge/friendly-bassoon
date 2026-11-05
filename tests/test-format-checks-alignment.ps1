# FR-012: Validate PDF report provenance against JSON and release version (PowerShell 5.1).
param(
 [string]$JsonPath=(Join-Path (Split-Path -Parent $PSScriptRoot) 'config\format-checks.json'),
 [string]$PdfPath=(Join-Path (Split-Path -Parent $PSScriptRoot) 'info/formatting-checks.pdf'),
 [string]$Version=''
)
$ErrorActionPreference='Stop'
try {
 if(-not(Test-Path -LiteralPath $JsonPath -PathType Leaf)){throw "JSON file missing: $JsonPath"}
 if(-not(Test-Path -LiteralPath $PdfPath -PathType Leaf)){throw "PDF file missing: $PdfPath"}
 $bytes=[IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $JsonPath).Path)
 $checks=(Get-Content -LiteralPath $JsonPath -Raw|ConvertFrom-Json).checks
 $seen=@{}
 foreach($c in $checks){
  $id=[string]$c.id
  if([string]::IsNullOrWhiteSpace($id) -or $seen.ContainsKey($id)){throw "Missing or duplicate check ID: $id"}
  $seen[$id]=$true
  if($c.status -eq 'planned' -and $c.enabled){throw "Planned check enabled: $id"}
 }
 if(-not $Version){
  $spec=Get-Content -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'docs\functional-specification.md') -Raw
  $match=[regex]::Match($spec,'(?m)^\*\*Version:\*\* (\d+\.\d+\.\d+)')
  if(-not $match.Success){throw 'Release version not found'}
  $Version=$match.Groups[1].Value
 }
 $hash=[BitConverter]::ToString(([Security.Cryptography.SHA256]::Create()).ComputeHash($bytes)).Replace('-','').ToLowerInvariant()
 $pdfBytes=[IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $PdfPath).Path)
 if($pdfBytes.Length -lt 500 -or [Text.Encoding]::ASCII.GetString($pdfBytes,0,5) -ne '%PDF-'){throw 'Invalid PDF'}
 $pdf=[Text.Encoding]::ASCII.GetString($pdfBytes)
 if(-not $pdf.Contains("VA-JSON-SHA256: $hash")){throw 'PDF JSON hash differs'}
 if(-not $pdf.Contains("VA-VERSION: $Version")){throw 'PDF version differs'}
 if(-not $pdf.Contains("Formatting checks for v$Version")){throw 'PDF title differs'}
 Write-Host 'FR-012 PASS: PDF title, version and JSON hash aligned'
 exit 0
} catch {
 Write-Error "FR-012 PDF alignment failed: $($_.Exception.Message)"
 exit 1
}
