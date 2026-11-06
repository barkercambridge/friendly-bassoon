# FR-013: Application-specific acceptance and release evidence.
# FR-001 through FR-007, FR-009 through FR-012; DevStan R08: Execute mapped Windows Word acceptance tests.
# Automated Windows Word Interop acceptance tests. Run in an interactive Windows session.
param(
 [string]$EnginePath=(Join-Path (Split-Path -Parent $PSScriptRoot) 'src\compare-formatting.ps1'),
 [string]$ResultsDirectory=(Join-Path $PSScriptRoot 'results'),
 [string]$AcceptanceZipPath='',
 [ValidateRange(10,1800)][int]$EngineTimeoutSeconds=20
)
$ErrorActionPreference='Stop'
$packageRoot=Split-Path -Parent $PSScriptRoot
$buildMetadataPath=Join-Path $packageRoot 'config\\virtual-admin-build.json'
$buildMetadata=$null
$sourceCommit=$null
$packageSha256=$null
$run=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
New-Item -ItemType Directory -Force -Path $ResultsDirectory | Out-Null
Get-ChildItem -LiteralPath $ResultsDirectory -Force | Remove-Item -Recurse -Force
$coverageDirectory=Join-Path ([IO.Path]::GetTempPath()) ('virtual-admin-coverage-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $coverageDirectory -Force | Out-Null
$results=New-Object 'System.Collections.Generic.List[object]'
$word=$null
$work=Join-Path ([IO.Path]::GetTempPath()) ('virtual-admin-test-'+[guid]::NewGuid().ToString('N'))
$ids=@('AT-001','AT-002','AT-003','AT-004','AT-005','AT-006','AT-007','AT-008','AT-010','AT-011')
$traceability=Get-Content -LiteralPath (Join-Path $packageRoot 'config\traceability.json') -Raw | ConvertFrom-Json
$mapping=@{}
foreach($requirement in $traceability.requirements){foreach($testId in @($requirement.tests)){if(-not $mapping.ContainsKey($testId)){$mapping[$testId]=@()};$mapping[$testId]+=[string]$requirement.id}}
foreach($testId in $ids){if(-not $mapping.ContainsKey($testId)){throw "Mandatory acceptance test has no FR mapping: $testId"}}
function Record([string]$id,[string]$status,[string]$detail) {
 $script:results.Add([pscustomobject]@{test_id=$id;requirements=@($script:mapping[$id]);status=$status;details=$detail})
}
function Assert([bool]$ok,[string]$message) {if(-not $ok){throw $message}}
function Write-Stage([string]$message) {
 Write-Host ('[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'),$message)
}
function MakeDoc([string]$path,[string]$kind) {
 $d=$script:word.Documents.Add()
 try {
  $body=if($kind -eq 'text'){"This is changed example text`rSecond paragraph text"}else{"This is some example text`rSecond paragraph text"}
  $d.Content.Text=$body
  if($kind -eq 'font'){$d.Range(13,20).Font.Name='Courier New'}
  if($kind -eq 'size'){$d.Range(13,20).Font.Size=16}
  if($kind -eq 'bold'){$d.Range(13,20).Font.Bold=-1}
  if($kind -eq 'italic'){$d.Range(13,20).Font.Italic=-1}
  $d.SaveAs2($path,16) # wdFormatXMLDocument: create a genuine .docx fixture
 } finally {$d.Close($false)}
}
function Highlighted([string]$path,[string]$term) {
 $d=$script:word.Documents.Open($path,$false,$true)
 try {
  $index=$d.Content.Text.IndexOf($term,[StringComparison]::Ordinal)
  if($index -lt 0){return $false}
  for($i=$index;$i -lt $index+$term.Length;$i++){
   if($d.Range($i,$i+1).HighlightColorIndex -ne 3){return $false}
  }
  return $true
 } finally {$d.Close($false)}
}
function RunEngine([string]$reference,[string]$target,[string]$specification=$null,[string]$engineOverride=$null) {
 $process=$null
 $stdout=''
 $stderr=''
 try {
  # Only record coverage for the unmodified engine shipped in the acceptance ZIP.
  $arguments=if($engineOverride){@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$engineOverride,'-TemplatePath',$reference,'-DocumentPath',$target)}else{@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',(Join-Path $script:PSScriptRoot 'measure-code-coverage.ps1'),'-EnginePath',$script:EnginePath,'-CoverageDirectory',$script:coverageDirectory,'-TemplatePath',$reference,'-DocumentPath',$target)}
  if($specification){$arguments+=@('-SpecificationPath',$specification)}
  $quotedArguments=@($arguments | ForEach-Object { '"' + ([string]$_).Replace('"','\\"') + '"' })
  $startInfo=New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName='powershell.exe'
  $startInfo.Arguments=$quotedArguments -join ' '
  $startInfo.UseShellExecute=$false
  $startInfo.CreateNoWindow=$true
  $startInfo.RedirectStandardOutput=$true
  $startInfo.RedirectStandardError=$true
  $process=New-Object System.Diagnostics.Process
  $process.StartInfo=$startInfo
  Write-Stage "Starting comparison engine (timeout: $($script:EngineTimeoutSeconds) seconds)."
  if(-not $process.Start()){throw 'Unable to start comparison engine process.'}
  $stdoutTask=$process.StandardOutput.ReadToEndAsync()
  $stderrTask=$process.StandardError.ReadToEndAsync()
  if(-not $process.WaitForExit($script:EngineTimeoutSeconds * 1000)) {
   try {$process.Kill();[void]$process.WaitForExit(10000)} catch {}
   throw "Comparison engine timed out after $($script:EngineTimeoutSeconds) seconds."
  }
  $process.WaitForExit()
  $stdout=$stdoutTask.Result
  $stderr=$stderrTask.Result
  $exitCode=$process.ExitCode
  return [pscustomobject]@{exit_code=$exitCode;message=($stdout+[Environment]::NewLine+$stderr)}
 } finally {
  if($null -ne $process){$process.Dispose()}
 }
}
try {
 Write-Stage 'Starting Virtual Admin acceptance tests.'
 Write-Stage 'Checking package provenance metadata.'
 if(-not(Test-Path -LiteralPath $buildMetadataPath)){throw 'Package provenance file config/virtual-admin-build.json is missing'}
 $buildMetadata=Get-Content -LiteralPath $buildMetadataPath -Raw | ConvertFrom-Json
 if($buildMetadata.application -ne 'virtual-admin' -or $buildMetadata.version -notmatch '^\d+\.\d+$' -or $buildMetadata.source_commit -notmatch '^[0-9a-f]{40}$'){
  throw 'Package provenance file is invalid or incomplete'
 }
 $sourceCommit=$buildMetadata.source_commit
 $zipName='virtual-admin-acceptance-v'+$buildMetadata.version+'.zip'
 if(-not $AcceptanceZipPath){$AcceptanceZipPath=Join-Path (Split-Path -Parent $packageRoot) $zipName}
 if(-not(Test-Path -LiteralPath $AcceptanceZipPath -PathType Leaf)){throw ('Original acceptance ZIP required for checksum provenance: '+$AcceptanceZipPath)}
 $packageSha256=(Get-FileHash -LiteralPath $AcceptanceZipPath -Algorithm SHA256).Hash.ToLowerInvariant()

 $specification=Join-Path $packageRoot 'config\format-checks.json'
 Assert (Test-Path -LiteralPath $specification) 'Machine-readable format-check specification is missing'
 $formatSpec=Get-Content -LiteralPath $specification -Raw | ConvertFrom-Json
 Write-Stage 'Checking extracted release package layout (AT-011).'
 try {
  $releaseRequired=@(
   'tests/measure-code-coverage.ps1','tests/compile-code-coverage.ps1',
   'run-virtual-admin.bat','run-acceptance-tests.bat',
   'src/compare-formatting.ps1','src/archive-previous-outputs.ps1',
   'config/format-checks.json','info/formatting-checks.pdf','config/virtual-admin-build.json',
   'docs/README.md','docs/installation.md','docs/functional-specification.md','docs/AGENTS.md','docs/traceability.json',
   'tests/test-functional-acceptance.ps1','tests/test-format-checks-alignment.ps1'
  )
  foreach($entry in $releaseRequired) {
   Assert (Test-Path -LiteralPath (Join-Path $packageRoot $entry) -PathType Leaf) ("Release package missing: "+$entry)
  }
  $rootNonBatch=@(Get-ChildItem -LiteralPath $packageRoot -File | Where-Object {$_.Extension -ne '.bat'})
  Assert ($rootNonBatch.Count -eq 0) ('Unexpected files at package root: '+($rootNonBatch.Name -join ', '))
  Assert (@(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'info') -Filter 'formatting-checks.pdf' -File).Count -eq 1) 'Expected exactly one PDF register in info/'
  Assert (-not (Test-Path -LiteralPath (Join-Path $packageRoot 'info/release.pdf'))) 'Acceptance package must not contain production-only release.pdf'
  Record 'AT-011' 'PASS' 'Extracted release has required subdirectories, PDF register in info/ and no other root-level files'
 } catch {Record 'AT-011' 'FAIL' $_.Exception.Message}
 Write-Stage 'Checking launcher and missing-input handling.'
 $launcher=Join-Path $packageRoot 'run-virtual-admin.bat'
 $launchContent=Get-Content -LiteralPath $launcher -Raw
 Assert ($launchContent -match '%~dp0\*\.dotx' -and $launchContent -match '%~dp0\*\.docx' -and $launchContent -match '/on') 'Launcher must select first alphabetically sorted DOTX and DOCX'
 Assert ($launchContent.Contains('-LauncherDirectory "%%~dp0."'.Replace('%%','%'))) 'Launcher must pass archive directory without a trailing backslash before the closing quote'
 Record 'AT-007' 'PASS' 'Launcher selects first alphabetically sorted DOTX and DOCX beside launcher (Word execution not checked)'
 $launcherDir=Join-Path $work 'launcher-negative'
 New-Item -ItemType Directory -Force -Path $launcherDir | Out-Null
 Copy-Item -LiteralPath $launcher -Destination (Join-Path $launcherDir 'run-virtual-admin.bat')
 $fixtureSrc=Join-Path $launcherDir 'src'
 New-Item -ItemType Directory -Force -Path $fixtureSrc | Out-Null
 Copy-Item -LiteralPath (Join-Path $packageRoot 'src/archive-previous-outputs.ps1') -Destination (Join-Path $fixtureSrc 'archive-previous-outputs.ps1')
 $cmd=Join-Path $launcherDir 'run-virtual-admin.bat'
 $missingBoth=& cmd.exe /d /c ('"'+$cmd+'"') 2>&1
 Assert ($LASTEXITCODE -ne 0 -and (($missingBoth|Out-String) -match 'No [.]dotx approved template')) 'Missing both files did not fail'
 Set-Content -LiteralPath (Join-Path $launcherDir 'a.dotx') -Value 'dummy'
 $missingTarget=& cmd.exe /d /c ('"'+$cmd+'"') 2>&1
 Assert ($LASTEXITCODE -ne 0 -and (($missingTarget|Out-String) -match 'No [.]docx document to check')) 'Missing DOCX did not fail'
 Remove-Item -LiteralPath (Join-Path $launcherDir 'a.dotx')
 Set-Content -LiteralPath (Join-Path $launcherDir 'b.docx') -Value 'dummy'
 $missingTemplate=& cmd.exe /d /c ('"'+$cmd+'"') 2>&1
 Assert ($LASTEXITCODE -ne 0 -and (($missingTemplate|Out-String) -match 'No [.]dotx approved template')) 'Missing DOTX did not fail'
 Record 'AT-006' 'PASS' 'Missing input combinations return nonzero with error'
 Write-Stage 'Preparing isolated Word test workspace.'
 $EnginePath=(Resolve-Path -LiteralPath $EnginePath).Path
 New-Item -ItemType Directory -Path $work -Force|Out-Null
 Write-Stage 'Measuring released archive helper during an isolated archival fixture.'
 $archiveFixture=Join-Path $work 'archive-coverage'
 New-Item -ItemType Directory -Path $archiveFixture -Force | Out-Null
 Set-Content -LiteralPath (Join-Path $archiveFixture 'activity.docx') -Value 'archival fixture'
 $archiveScript=Join-Path $packageRoot 'src/archive-previous-outputs.ps1'
 & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'measure-code-coverage.ps1') -EnginePath $archiveScript -CoverageDirectory $coverageDirectory -LauncherDirectory $archiveFixture
 Assert ($LASTEXITCODE -eq 0) 'Archive helper coverage fixture failed'
 Assert (@(Get-ChildItem -LiteralPath (Join-Path $archiveFixture 'old') -Filter 'activity-*.docx' -File).Count -eq 1) 'Archive helper did not preserve existing output'
 Write-Stage 'Checking PDF and JSON register alignment (AT-010).'
 try {
  $alignmentScript=Join-Path $PSScriptRoot 'test-format-checks-alignment.ps1'
  $pdfRegister=Join-Path $packageRoot 'info/formatting-checks.pdf'
  Assert (Test-Path -LiteralPath $alignmentScript) 'Alignment verifier script is missing'
  $alignmentOutput=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $alignmentScript -JsonPath $specification -PDFPath $pdfRegister -Version $buildMetadata.version 2>&1
  Assert ($LASTEXITCODE -eq 0) ('Matching JSON and PDF were rejected: '+($alignmentOutput|Out-String))
  $modified=Get-Content -LiteralPath $specification -Raw|ConvertFrom-Json
  $modified.checks[0].description=[string]$modified.checks[0].description+' - deliberate acceptance mismatch'
  $misaligned=Join-Path $work 'misaligned-format-checks.json'
  $modified|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $misaligned -Encoding UTF8
  # A deliberately rejected native PowerShell process writes to stderr. Collect
  # the exit code without letting redirected stderr abort this test runner.
  $priorErrorPreference=$ErrorActionPreference
  try {
   $ErrorActionPreference='Continue'
   $rejected=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $alignmentScript -JsonPath $misaligned -PDFPath $pdfRegister -Version $buildMetadata.version 2>&1
   $rejectedExitCode=$LASTEXITCODE
  } finally { $ErrorActionPreference=$priorErrorPreference }
  Assert ($rejectedExitCode -ne 0) 'Misaligned JSON and PDF were incorrectly accepted'
  Record 'AT-010' 'PASS' 'All register entries aligned; deliberately mismatched description rejected'
 } catch {Record 'AT-010' 'FAIL' $_.Exception.Message}
 Write-Stage 'Starting Microsoft Word COM automation.'
 $word=New-Object -ComObject Word.Application
 $word.Visible=$false
 $word.DisplayAlerts=0
 Write-Stage 'Creating baseline Word document.'
 $template=Join-Path $work 'template.docx'
 MakeDoc $template 'template'
 # FR-004, FR-011: Use the shipped CHAR-001-only configuration for acceptance.
 $fixtureSpec=Join-Path $work 'acceptance-format-checks.json'
 $fixtureConfiguration=Get-Content -LiteralPath $specification -Raw | ConvertFrom-Json
 Assert ($fixtureConfiguration.checks.Count -eq 1 -and $fixtureConfiguration.checks[0].id -eq 'CHAR-001' -and $fixtureConfiguration.checks[0].enabled) 'CHAR-001 must be the only configured formatting check'
 $fixtureConfiguration|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $fixtureSpec -Encoding UTF8
 Write-Stage 'Running comparison-execution failure test (AT-008).'
 try {
  $failureTarget=Join-Path $work 'comparison-failure.docx'
  MakeDoc $failureTarget 'font'
  $beforeTarget=(Get-FileHash -LiteralPath $failureTarget -Algorithm SHA256).Hash
  $beforeTemplate=(Get-FileHash -LiteralPath $template -Algorithm SHA256).Hash
  $injectedEngine=Join-Path $work 'compare-formatting-injected.ps1'
  $originalEngine=Get-Content -LiteralPath $EnginePath -Raw
  $anchor='$expectedFont = Get-StyleFontProperties $reference $t'
  Assert ($originalEngine.Contains($anchor)) 'Cannot locate comparison property-read injection point'
  $replacement="if (`$check.id -eq 'CHAR-001' -and `$i -eq 2) { throw 'AT-008 simulated formatting property read failure' }; "+$anchor
  Set-Content -LiteralPath $injectedEngine -Value $originalEngine.Replace($anchor,$replacement) -Encoding UTF8
  $failureRun=RunEngine $template $failureTarget $fixtureSpec $injectedEngine
  Assert ($failureRun.exit_code -ne 0) 'Simulated formatting execution failure did not fail'
  $errorsPath=Join-Path $work 'activity.docx'
  Assert (Test-Path -LiteralPath $errorsPath) 'activity.docx was not generated'
  $errorDoc=$word.Documents.Open($errorsPath,$false,$true)
  try {$errorText=[string]$errorDoc.Content.Text} finally {$errorDoc.Close($false)}
  Assert ($errorText.IndexOf('Errors') -lt $errorText.IndexOf('Summary of changes') -and $errorText -match 'Paragraph 1' -and $errorText -match 'example' -and $errorText -match 'CHAR-001' -and $errorText -match 'font family, size, bold and italic against corresponding template style' -and $errorText -match 'AT-008 simulated formatting property read failure') 'activity.docx lacks attempted comparison and failure reason'
  Assert ((Get-FileHash -LiteralPath $failureTarget -Algorithm SHA256).Hash -eq $beforeTarget) 'Failure test modified target input'
  Assert ((Get-FileHash -LiteralPath $template -Algorithm SHA256).Hash -eq $beforeTemplate) 'Failure test modified template input'
  Record 'AT-008' 'PASS' 'Activity report retained detected formatting difference and failed-check diagnostic; inputs preserved'
 } catch {Record 'AT-008' 'FAIL' $_.Exception.Message}
 # FR-005, FR-011: Clear the preceding test fixture report, never overwrite it in the engine.
 if(Test-Path -LiteralPath (Join-Path $work 'activity.docx')) { Remove-Item -LiteralPath (Join-Path $work 'activity.docx') -Force }
 $cases=@('font','size','bold','italic','text')
 $passedCases=@{}
 $formatFailures=New-Object 'System.Collections.Generic.List[string]'
 foreach($kind in $cases) {
  Write-Stage "Running $kind comparison test."
  $id=switch($kind){'font'{'AT-002'}'size'{'AT-002'}'bold'{'AT-002'}'italic'{'AT-002'}'text'{'AT-005'}}
  try {
   # Each fixture starts without a report; the engine must refuse overwrites.
   $priorActivity=Join-Path $work 'activity.docx'
   if(Test-Path -LiteralPath $priorActivity){Remove-Item -LiteralPath $priorActivity -Force}
   $target=Join-Path $work ($kind+'.docx')
   MakeDoc $target $kind
   $before=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
   $referenceBefore=(Get-FileHash -LiteralPath $template -Algorithm SHA256).Hash
   $r=RunEngine $template $target $fixtureSpec
   Assert ($r.exit_code -eq 0) ('Engine exited with code '+$r.exit_code+'. Engine output: '+$r.message)
   $marked=Join-Path $work ($kind+'-HIGHLIGHT.docx')
   $report=Join-Path $work 'activity.docx'
   Assert (Test-Path -LiteralPath $marked) 'Highlighted copy missing'
   Assert (Test-Path -LiteralPath $report) 'Activity report missing'
   $activity=$word.Documents.Open($report,$false,$true)
   try {$reportText=[string]$activity.Content.Text} finally {$activity.Close($false)}
   Assert ($reportText -match 'Errors' -and $reportText -match 'Summary of changes' -and $reportText.IndexOf('Errors') -lt $reportText.IndexOf('Summary of changes')) 'Activity report sections missing or out of order'
    # FR-005: The summary is a Word table before the diagnostic sections.
    Assert ($reportText -match 'Comparison started \(UTC\)' -and $reportText -match 'Elapsed comparison time' -and $reportText -match 'Paragraphs compared' -and $reportText -match 'Total paragraphs' -and $reportText -match 'Findings') 'Activity summary fields missing'
    Assert ($reportText.IndexOf('Comparison started (UTC)') -lt $reportText.IndexOf('Errors')) 'Activity summary must precede Errors'
   Assert ($reportText -match 'None') 'Successful activity report must show no errors'
   Assert (-not (Test-Path -LiteralPath (Join-Path $work ($kind+' - differences.txt')))) 'Legacy differences TXT was generated'
   switch($kind){
    {$_ -in @('font','size','bold','italic')}{Assert (Highlighted $marked 'example') 'Incorrect font property not highlighted'; Assert ($reportText -match 'Paragraph 1' -and $reportText -match 'example') 'Formatting difference missing from activity report'}
    'text'{Assert (($reportText -match 'Paragraph 1') -and (Highlighted $marked 'changed')) 'Text mismatch not reported/highlighted'}
   }
   Assert ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $before) 'Input changed'
   Assert ((Get-FileHash -LiteralPath $template -Algorithm SHA256).Hash -eq $referenceBefore) 'Template changed'
   $passedCases[$kind]=$true
   if($kind -eq 'text'){Record $id 'PASS' ('Verified '+$kind+' difference and input integrity')}
  } catch {
   if($kind -eq 'text'){Record $id 'FAIL' $_.Exception.Message}
   else {$formatFailures.Add($kind+': '+$_.Exception.Message)}
  }
 }
 if($formatFailures.Count -gt 0){Record 'AT-002' 'FAIL' ($formatFailures -join '; ')}
 elseif(@(@('font','size','bold','italic') | Where-Object {-not $passedCases.ContainsKey($_)}).Count -gt 0){Record 'AT-002' 'FAIL' 'One or more formatting fixtures did not complete'}
 else {Record 'AT-002' 'PASS' 'Font family, size, bold and italic differences highlighted; inputs preserved'}
 Write-Stage 'Checking that existing output is not overwritten (AT-003).'
 try {
  Assert ($passedCases.ContainsKey('font')) 'Font fixture did not produce a verified output'
  $markedPath=Join-Path $work 'font-HIGHLIGHT.docx'
  $activityPath=Join-Path $work 'activity.docx'
  $markedHash=(Get-FileHash -LiteralPath $markedPath -Algorithm SHA256).Hash
  $activityHash=(Get-FileHash -LiteralPath $activityPath -Algorithm SHA256).Hash
  $r=RunEngine $template (Join-Path $work 'font.docx') $fixtureSpec
  Assert ($r.exit_code -ne 0) 'Existing highlighted output was overwritten'
  Assert ((Get-FileHash -LiteralPath $markedPath -Algorithm SHA256).Hash -eq $markedHash) 'Existing highlighted output changed'
  Assert ((Get-FileHash -LiteralPath $activityPath -Algorithm SHA256).Hash -eq $activityHash) 'Existing activity report changed'
  Remove-Item -LiteralPath $markedPath -Force
  $r=RunEngine $template (Join-Path $work 'bold.docx')
  Assert ($r.exit_code -ne 0) 'Existing activity report was overwritten'
  Assert (-not (Test-Path -LiteralPath $markedPath)) 'Engine created highlighted copy despite existing activity report'
  Assert ((Get-FileHash -LiteralPath $activityPath -Algorithm SHA256).Hash -eq $activityHash) 'Existing activity report was overwritten'
  # Launcher archival: preserve both outputs with timestamped names in old/.
  $archiveFixture=Join-Path $work 'archive-fixture'
  New-Item -ItemType Directory -Path $archiveFixture -Force | Out-Null
  $previousMarked=Join-Path $archiveFixture 'sample-HIGHLIGHT.docx'
  $previousActivity=Join-Path $archiveFixture 'activity.docx'
  [IO.File]::WriteAllText($previousMarked,'previous highlighted content')
  [IO.File]::WriteAllText($previousActivity,'previous activity content')
  $archiveScript=Join-Path $PSScriptRoot '..\\src\\archive-previous-outputs.ps1'
  & $archiveScript -LauncherDirectory $archiveFixture
  Assert (-not (Test-Path -LiteralPath $previousMarked) -and -not (Test-Path -LiteralPath $previousActivity)) 'Previous outputs were not archived'
  $oldFolder=Join-Path $archiveFixture 'old'
  $saved=@(Get-ChildItem -LiteralPath $oldFolder -File)
  Assert ($saved.Count -eq 2) 'Expected two archived documents'
  Assert (@($saved | Where-Object { $_.Name -match '^sample-HIGHLIGHT-\d{8}-\d{6}-\d{3}(?:-\d+)?[.]docx$' }).Count -eq 1) 'Highlighted archive timestamp missing'
  Assert (@($saved | Where-Object { $_.Name -match '^activity-\d{8}-\d{6}-\d{3}(?:-\d+)?[.]docx$' }).Count -eq 1) 'Activity archive timestamp missing'
  Assert (@($saved | Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -match 'previous' }).Count -eq 2) 'Archived content was altered'
  Record 'AT-003' 'PASS' 'Engine overwrite refusal and launcher timestamped archival verified'
 } catch {Record 'AT-003' 'FAIL' $_.Exception.Message}
 if($passedCases.Count -eq $cases.Count){
  Record 'AT-001' 'PASS' 'Word COM and comparison engine ran'
  Record 'AT-004' 'PASS' 'Highlighted document and activity report generated and checked'
 }else{
  Record 'AT-001' 'FAIL' 'Not all Word integration cases succeeded'
  Record 'AT-004' 'FAIL' 'Not all comparison reports verified'
 }
} catch {
 foreach($id in $ids){if(-not @($results|Where-Object test_id -eq $id).Count){Record $id 'BLOCKED' ('Test setup unavailable: '+$_.Exception.Message)}}
} finally {
 Write-Stage 'Finalising Word automation and writing evidence.'
 $wordVersion=$null
 if($null -ne $word){try{$wordVersion=[string]$word.Version}catch{}}
 if($null -ne $word){try{$word.Quit()}catch{}}
 if($null -ne $word -and [Runtime.InteropServices.Marshal]::IsComObject($word)){[void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)}
 [GC]::Collect();[GC]::WaitForPendingFinalizers()
 if(Test-Path -LiteralPath $work){try{Remove-Item -LiteralPath $work -Recurse -Force}catch{Record 'CLEANUP' 'FAIL' $_.Exception.Message}}
 foreach($id in $ids){if(-not @($results|Where-Object test_id -eq $id).Count){Record $id 'BLOCKED' 'Test was not executed'}}
 $pass=@($results|Where-Object status -eq 'PASS').Count
 $fail=@($results|Where-Object status -eq 'FAIL').Count
 $blocked=@($results|Where-Object status -eq 'BLOCKED').Count
 $evidenceVersion=$null
 if($null -ne $buildMetadata){$evidenceVersion=$buildMetadata.version}
 $record=[ordered]@{application='virtual-admin';version=$evidenceVersion;source_commit=$sourceCommit;release_input_fingerprint=$buildMetadata.release_input_fingerprint;acceptance_zip_sha256=$packageSha256;run_id=$run;timestamp_utc=(Get-Date).ToUniversalTime().ToString('o');computer=$env:COMPUTERNAME;operating_system=[Environment]::OSVersion.VersionString;powershell=$PSVersionTable.PSVersion.ToString();word_version=$wordVersion;engine_path=$EnginePath;passed=$pass;failed=$fail;blocked=$blocked;tests=@($results.ToArray())}
 try {
  & (Join-Path $PSScriptRoot 'compile-code-coverage.ps1') -PackageRoot $packageRoot -ResultsDirectory $ResultsDirectory -CoverageDirectory $coverageDirectory -Version $evidenceVersion -SourceCommit $sourceCommit -AcceptanceZipSha256 $packageSha256
  $coverageDiagnostics=Get-Content -LiteralPath (Join-Path $ResultsDirectory 'coverage-diagnostics.json') -Raw | ConvertFrom-Json
  if($coverageDiagnostics.status -ne 'PASS'){
   Write-Warning 'Coverage measurement failed; see coverage-diagnostics.json'
   $fail++
   $record.failed=$fail
  }
 } catch {
  Write-Warning ("Coverage collection failed: "+$_.Exception.Message)
  $fail++
  $record.failed=$fail
 }
 if(Test-Path -LiteralPath $coverageDirectory){
  if($fail -gt 0){
   $diagnosticHits=Join-Path $ResultsDirectory 'coverage-hit-files'
   New-Item -ItemType Directory -Path $diagnosticHits -Force | Out-Null
   Copy-Item -Path (Join-Path $coverageDirectory '*.hits') -Destination $diagnosticHits -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $coverageDirectory -Recurse -Force -ErrorAction SilentlyContinue
 }
 $base=Join-Path $ResultsDirectory 'acceptance-results'
 $record|ConvertTo-Json -Depth 8|Set-Content -LiteralPath ($base+'.json') -Encoding UTF8
 Write-Host "Evidence: $base.json"
 Write-Host "PASS=$pass FAIL=$fail BLOCKED=$blocked"
 if($fail -gt 0 -or $blocked -gt 0){exit 1}
}
