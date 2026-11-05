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
# Verify breakpoint callbacks in the same Windows PowerShell process before measuring released code.
$probe=Join-Path $CoverageDirectory ('coverage-probe-'+[guid]::NewGuid().ToString('N')+'.ps1')
$probeHits=Join-Path $CoverageDirectory ('coverage-probe-'+[guid]::NewGuid().ToString('N')+'.hits')
[IO.File]::WriteAllText($probe, '$coverageProbeValue = 1' + [Environment]::NewLine)
$probeBreakpoint=$null
try {
 $probeBreakpoint=Set-PSBreakpoint -Script $probe -Line 1 -Action {
  [IO.File]::AppendAllText($probeHits, '1'+[Environment]::NewLine)
 }
 & $probe
 if(-not (Test-Path -LiteralPath $probeHits) -or -not ((Get-Content -LiteralPath $probeHits -Raw) -match '(?m)^1\s*
 foreach($line in $lines){
  $breakpoints+=Set-PSBreakpoint -Script $engine -Line $line -Action {
   [System.IO.File]::AppendAllText($env:VA_COVERAGE_HITS,([string]$PSDebugContext.Breakpoint.Line+[Environment]::NewLine))
  }
 }
 if($LauncherDirectory){$arguments=@{LauncherDirectory=$LauncherDirectory}}else{$arguments=@{TemplatePath=$TemplatePath;DocumentPath=$DocumentPath}}
 if($SpecificationPath){$arguments.SpecificationPath=$SpecificationPath}
 & $engine @arguments
} finally {
 if($breakpoints.Count -gt 0){$breakpoints | Remove-PSBreakpoint}
}
)) {
  throw 'Coverage breakpoint self-test produced no numeric hit; instrumentation unavailable'
 }
} finally {
 if($probeBreakpoint){$probeBreakpoint | Remove-PSBreakpoint}
 Remove-Item -LiteralPath $probe,$probeHits -Force -ErrorAction SilentlyContinue
}
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
