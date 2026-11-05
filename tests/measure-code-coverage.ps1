# FR-013: Collect line-level execution evidence from the released comparison engine.
param(
 [Parameter(Mandatory=$true)][string]$EnginePath,
 [Parameter(Mandatory=$true)][string]$CoverageDirectory,
 [string]$TemplatePath,
 [string]$DocumentPath,
 [string]$SpecificationPath,
 [string]$LauncherDirectory
)
$ErrorActionPreference='Stop'
$engine=(Resolve-Path -LiteralPath $EnginePath).Path
New-Item -ItemType Directory -Path $CoverageDirectory -Force | Out-Null
$env:VA_COVERAGE_HITS=Join-Path $CoverageDirectory ($(if($LauncherDirectory){'archive-'}else{'engine-'})+[guid]::NewGuid().ToString('N')+'.hits')
$tokens=$null
$parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($engine,[ref]$tokens,[ref]$parseErrors)
if(@($parseErrors).Count -gt 0){throw 'Cannot instrument invalid PowerShell source'}
$lines=@($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.StatementAst]},$true) |
 ForEach-Object {$_.Extent.StartLineNumber} | Sort-Object -Unique)
if($lines.Count -eq 0){throw 'No executable statements identified'}
$breakpoints=@()
try {
 foreach($line in $lines){
  $breakpoints+=Set-PSBreakpoint -Script $engine -Line $line -Action {
   [System.IO.File]::AppendAllText($env:VA_COVERAGE_HITS,([string]$PSBreakpoint.Line+[Environment]::NewLine))
  }
 }
 if($LauncherDirectory){$arguments=@{LauncherDirectory=$LauncherDirectory}}else{$arguments=@{TemplatePath=$TemplatePath;DocumentPath=$DocumentPath}}
 if($SpecificationPath){$arguments.SpecificationPath=$SpecificationPath}
 & $engine @arguments
} finally {
 if($breakpoints.Count -gt 0){$breakpoints | Remove-PSBreakpoint}
}
