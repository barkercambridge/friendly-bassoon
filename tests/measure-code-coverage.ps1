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

# Check that breakpoint actions write numeric hit data before running the engine.
$probe=Join-Path $CoverageDirectory ('coverage-probe-'+[guid]::NewGuid().ToString('N')+'.ps1')
$env:VA_COVERAGE_PROBE_HITS=Join-Path $CoverageDirectory ('coverage-probe-'+[guid]::NewGuid().ToString('N')+'.hits')
[IO.File]::WriteAllText($probe, '$coverageProbeValue = 1' + [Environment]::NewLine)
$probeBreakpoint=$null
try {
 $probeBreakpoint=Set-PSBreakpoint -Script $probe -Line 1 -Action {
  [IO.File]::AppendAllText($env:VA_COVERAGE_PROBE_HITS, '1'+[Environment]::NewLine)
 }
 & $probe
 if(-not (Test-Path -LiteralPath $env:VA_COVERAGE_PROBE_HITS)){
  throw 'Coverage breakpoint self-test created no hit file'
 }
 if(-not ((Get-Content -LiteralPath $env:VA_COVERAGE_PROBE_HITS -Raw) -match '(?m)^1\s*$')){
  throw 'Coverage breakpoint self-test produced no numeric hit'
 }
} finally {
 if($probeBreakpoint){$probeBreakpoint | Remove-PSBreakpoint}
 Remove-Item -LiteralPath $probe,$env:VA_COVERAGE_PROBE_HITS -Force -ErrorAction SilentlyContinue
 Remove-Item Env:VA_COVERAGE_PROBE_HITS -ErrorAction SilentlyContinue
}
$breakpoints=@()
try {
 foreach($line in $lines){
  $breakpoints+=Set-PSBreakpoint -Script $engine -Line $line -Action {
   [IO.File]::AppendAllText($env:VA_COVERAGE_HITS,([string]$PSDebugContext.Breakpoint.Line+[Environment]::NewLine))
  }
 }
 if($LauncherDirectory){$arguments=@{LauncherDirectory=$LauncherDirectory}}else{$arguments=@{TemplatePath=$TemplatePath;DocumentPath=$DocumentPath}}
 if($SpecificationPath){$arguments.SpecificationPath=$SpecificationPath}
 & $engine @arguments
} finally {
 if($breakpoints.Count -gt 0){$breakpoints | Remove-PSBreakpoint}
}
