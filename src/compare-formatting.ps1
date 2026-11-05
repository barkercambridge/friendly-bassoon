 # FR-001, FR-007: Accept document and template paths for interactive Word comparison.
param(
    [Parameter(Mandatory=$true)][string]$TemplatePath,
    [Parameter(Mandatory=$true)][string]$DocumentPath,
    [string]$SpecificationPath,
    [ValidateRange(30,86400)][int]$ComparisonTimeoutSeconds = 1800
)
# Parameter default expressions are evaluated before $PSScriptRoot is populated
# in Windows PowerShell 5.1. Resolve the default only after script startup.
if ([string]::IsNullOrWhiteSpace($SpecificationPath)) {
    $scriptDirectory = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($scriptDirectory)) {
        $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $SpecificationPath = Join-Path (Split-Path -Parent $scriptDirectory) 'config\format-checks.json'
}
# FR-001, FR-007: Resolve inputs and execute the Word comparison under the interactive user.
# FR-004, FR-009: Compare formatting and detect structural mismatches.
# FR-006: Preserve inputs and reject an existing highlighted output.
# FR-005, FR-011: Write the consolidated activity report, including errors and changes.
$ErrorActionPreference = 'Stop'
$word = $null
$reference = $null
$target = $null
$findings = New-Object 'System.Collections.Generic.List[string]'
$configurationErrors = New-Object 'System.Collections.Generic.List[string]'
$changedParagraphs = New-Object 'System.Collections.Generic.List[object]'
# FR-005: Capture comparison metrics for the activity summary.
$comparisonTimer = $null
$comparisonStartedUtc = $null
$comparisonFinishedUtc = $null
$totalParagraphs = $null
$processedParagraphs = 0
$comparisonOutcome = 'Not started'
function Write-Stage([string]$message) {
    Write-Host ('[{0}] ENGINE: {1}' -f (Get-Date -Format 'HH:mm:ss'),$message)
}
function Test-UserCancellation {
    # Console input is unavailable in noninteractive acceptance tests and CI.
    # Poll without consuming ordinary keys; Escape requests a clean exit.
    try {
        if (-not [Console]::IsInputRedirected -and [Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq [ConsoleKey]::Escape) {
                throw [System.OperationCanceledException]::new('Comparison cancelled by user (Esc).')
            }
        }
    } catch [System.OperationCanceledException] {
        throw
    } catch [System.InvalidOperationException] {
        # No interactive console is attached.
    } catch [System.IO.IOException] {
        # Console input cannot be read in this host.
    }
}
# CHAR-001 is the sole configurable formatting check.
$requiredChecks = @('CHAR-001')
$allowed = @{ Character = @('Name', 'Size', 'Bold', 'Italic') }
# FR-004: Mark font family, size, bold and italic differences in the highlighted output copy.
function Highlight($range) { $range.HighlightColorIndex = 3 } # wdTurquoise
function ValuesEqual($left, $right) {
    return ([string]$left -ceq [string]$right)
}
function Get-StyleFontProperties($template, $paragraph) {
    # Resolve all four properties from the same named template style.
    $styleName = [string]$paragraph.Range.Style.NameLocal
    if ([string]::IsNullOrWhiteSpace($styleName)) { throw 'Paragraph style name is empty.' }
    $templateStyle = $template.Styles.Item($styleName)
    if ($null -eq $templateStyle) { throw "Template style '$styleName' was not found." }
    $font = $templateStyle.Font
    $name = [string]$font.Name
    $size = [double]$font.Size
    $bold = [int]$font.Bold
    $italic = [int]$font.Italic
    if ([string]::IsNullOrWhiteSpace($name) -or $name -eq '9999999' -or $name -eq '-2') {
        throw "Template style '$styleName' does not define an unambiguous font family."
    }
    if ($size -le 0 -or [double]::IsNaN($size) -or [double]::IsInfinity($size)) {
        throw "Template style '$styleName' does not define a valid font size."
    }
    if ($bold -notin @(-1, 0) -or $italic -notin @(-1, 0)) {
        throw "Template style '$styleName' has ambiguous bold or italic formatting."
    }
    return [pscustomobject]@{ Name=$name; Size=$size; Bold=$bold; Italic=$italic }
}
function Test-FontProperties($font, $expected) {
    $name = [string]$font.Name
    $size = [double]$font.Size
    $bold = [int]$font.Bold
    $italic = [int]$font.Italic
    # Word returns 9999999/-2 for mixed font names, 9999999 for mixed sizes,
    # and 9999999 for mixed bold/italic states. None is a definite match.
    if ([string]::IsNullOrWhiteSpace($name) -or $name -in @('9999999','-2')) { return $false }
    if ($size -le 0 -or [double]::IsNaN($size) -or [double]::IsInfinity($size)) { return $false }
    if ($bold -notin @(-1, 0) -or $italic -notin @(-1, 0)) { return $false }
    return ((ValuesEqual $name $expected.Name) -and
            ($size -eq $expected.Size) -and
            ($bold -eq $expected.Bold) -and
            ($italic -eq $expected.Italic))
}
 # FR-005, FR-011: Consolidate comparison findings and failed checks in activity.docx.
function Write-ActivityDocument($errors, $changes, $path, $templatePath, $documentPath) {
    # Build a minimal, valid DOCX package directly. Do not automate Word to
    # create diagnostic output: Word's SaveAs2 can block on hidden UI prompts.
    $archive = $null
    try {
        Write-Stage "Creating activity.docx package without Word automation: $path"
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $lines = @(
            'Virtual Admin - Activity report',
            "Generated: $((Get-Date).ToString('o'))",
            "Template: $templatePath",
            "Document: $documentPath",
            '',
            'Errors'
        )
        if (@($errors).Count -eq 0) { $lines += 'None.' }
        else { $lines += @($errors | ForEach-Object { "- $($_)" }) }
        $lines += @('', 'Summary of changes')
        # Changed paragraphs are rendered as complete text with highlighted runs below.
        # FR-005: Put a real Word table before the Errors and changes sections.
        $finishUtc = if ($null -ne $comparisonFinishedUtc) { $comparisonFinishedUtc } elseif ($null -ne $comparisonStartedUtc) { [DateTime]::UtcNow } else { $null }
        $elapsed = if ($null -ne $comparisonTimer) { ('{0:n1} seconds' -f $comparisonTimer.Elapsed.TotalSeconds) } else { 'Not available' }
        $started = if ($null -ne $comparisonStartedUtc) { $comparisonStartedUtc.ToString('o') } else { 'Not available' }
        $finished = if ($null -ne $finishUtc) { $finishUtc.ToString('o') } else { 'Not available' }
        $paragraphCount = if ($null -ne $totalParagraphs) { [string]$totalParagraphs } else { 'Not available' }
        $summaryRows = @(
            @('Status', [string]$comparisonOutcome),
            @('Comparison started (UTC)', $started),
            @('Comparison finished (UTC)', $finished),
            @('Elapsed comparison time', $elapsed),
            @('Paragraphs compared', [string]$processedParagraphs),
            @('Total paragraphs', $paragraphCount),
            @('Findings', [string]@($changes).Count),
            @('Errors', [string]@($errors).Count)
        )
        $tableRows = foreach ($pair in $summaryRows) {
            $cells = foreach ($value in $pair) {
                $escapedValue = [System.Security.SecurityElement]::Escape([string]$value)
                '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr><w:p><w:r><w:t xml:space="preserve">' + $escapedValue + '</w:t></w:r></w:p></w:tc>'
            }
            '<w:tr>' + ($cells -join '') + '</w:tr>'
        }
        $summaryTableXml = '<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/><w:tblBorders><w:top w:val="single"/><w:left w:val="single"/><w:bottom w:val="single"/><w:right w:val="single"/><w:insideH w:val="single"/><w:insideV w:val="single"/></w:tblBorders></w:tblPr><w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>' + ($tableRows -join '') + '</w:tbl>'
        $paragraphXml = foreach ($line in $lines) {
            $escaped = [System.Security.SecurityElement]::Escape([string]$line)
            if ([string]::IsNullOrEmpty($escaped)) { $escaped = '' }
            '<w:p><w:r><w:t xml:space="preserve">' + $escaped + '</w:t></w:r></w:p>'
        }
        $paragraphXml = @($paragraphXml)
        $paragraphXml = @($paragraphXml[0], $summaryTableXml) + @($paragraphXml | Select-Object -Skip 1)
        # FR-011: One entry per affected paragraph; never list individual characters.
        $changeXml = New-Object 'System.Collections.Generic.List[string]'
        foreach ($entry in $changedParagraphs) {
            $heading = [System.Security.SecurityElement]::Escape(('Paragraph {0}' -f $entry.Number))
            [void]$changeXml.Add('<w:p><w:r><w:t>' + $heading + '</w:t></w:r></w:p>')
            $content = [string]$entry.Text
            $marked = $entry.Marked
            $runs = New-Object 'System.Collections.Generic.List[string]'
            if ($content.Length -eq 0) {
                [void]$runs.Add('<w:r><w:t>[Empty paragraph]</w:t></w:r>')
            } else {
                $offset = 0
                while ($offset -lt $content.Length) {
                    $highlight = [bool]$marked[$offset]
                    $end = $offset + 1
                    while ($end -lt $content.Length -and [bool]$marked[$end] -eq $highlight) { $end++ }
                    $escaped = [System.Security.SecurityElement]::Escape($content.Substring($offset,$end-$offset))
                    $style = if ($highlight) { '<w:rPr><w:shd w:val="clear" w:color="auto" w:fill="ADD8E6"/></w:rPr>' } else { '' }
                    [void]$runs.Add('<w:r>' + $style + '<w:t xml:space="preserve">' + $escaped + '</w:t></w:r>')
                    $offset = $end
                }
            }
            [void]$changeXml.Add('<w:p>' + ($runs -join '') + '</w:p>')
        }
        if ($changeXml.Count -eq 0) { [void]$changeXml.Add('<w:p><w:r><w:t>No differences recorded.</w:t></w:r></w:p>') }
        $paragraphXml += @($changeXml.ToArray())
        $documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
            '<w:body>' + ($paragraphXml -join '') +
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>' +
            '</w:body></w:document>'
        $contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
            '<Default Extension="xml" ContentType="application/xml"/>' +
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
            '</Types>'
        $rootRelationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
            '</Relationships>'
        # FR-006: Never delete or replace an existing activity report.
        if (Test-Path -LiteralPath $path) { throw "Activity report already exists: $path" }
        $archive = [System.IO.Compression.ZipFile]::Open($path, [System.IO.Compression.ZipArchiveMode]::Create)
        $parts = @(
            @{ Name='[Content_Types].xml'; Content=$contentTypes },
            @{ Name='_rels/.rels'; Content=$rootRelationships },
            @{ Name='word/document.xml'; Content=$documentXml }
        )
        foreach ($part in $parts) {
            $entry = $archive.CreateEntry($part.Name)
            $stream = $entry.Open()
            try {
                $writer = New-Object System.IO.StreamWriter($stream, (New-Object System.Text.UTF8Encoding($false)))
                try { $writer.Write($part.Content) } finally { $writer.Dispose() }
            } finally {
                if ($null -ne $stream) { $stream.Dispose() }
            }
        }
        Write-Stage 'activity.docx package written.'
    } finally {
        if ($null -ne $archive) { $archive.Dispose() }
    }
}
 # FR-004, FR-011: Validate the configured checks and collect unsupported-check errors.
function Load-CheckSpecification($path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $configurationErrors.Add("Specification file is missing: $path")
        return @()
    }
    Write-Stage "Loading format-check specification: $path"
    try { $spec = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
    catch {
        $configurationErrors.Add("Specification JSON is invalid: $($_.Exception.Message)")
        return @()
    }
    if ($spec.schema_version -ne 1 -or $null -eq $spec.checks) {
        $configurationErrors.Add('Specification must contain schema_version 1 and a checks array.')
        return @()
    }
    $seen = @{}
    foreach ($check in $spec.checks) {
        if ([string]::IsNullOrWhiteSpace([string]$check.id) -or [string]::IsNullOrWhiteSpace([string]$check.scope) -or ($check.status -ne 'planned' -and [string]::IsNullOrWhiteSpace([string]$check.property))) {
            $configurationErrors.Add('A check is missing its id, scope or property.')
            continue
        }
        $id = [string]$check.id
        if ($seen.ContainsKey($id)) {
            $configurationErrors.Add("Duplicate check ID: $id")
            continue
        }
        $seen[$id] = $true
        if ($check.status -eq 'planned') {
            if ($check.enabled -eq $true) { $configurationErrors.Add("Planned check $id must be disabled.") }
            continue
        }
        if ($null -eq $check.enabled -or $check.enabled -isnot [bool]) { $configurationErrors.Add("Check $id must define a boolean enabled value.") }
        if (-not $allowed.ContainsKey([string]$check.scope)) {
            $configurationErrors.Add("Check $id uses unsupported scope '$($check.scope)'.")
        } elseif ($allowed[[string]$check.scope] -notcontains [string]$check.property) {
            $configurationErrors.Add("Check $id uses unsupported property '$($check.property)' for scope '$($check.scope)'.")
        }
    }
    foreach ($id in $requiredChecks) {
        if (-not $seen.ContainsKey($id)) { $configurationErrors.Add("Required check is missing: $id") }
    }
    foreach ($id in @($seen.Keys)) {
        if ($requiredChecks -notcontains $id) { $configurationErrors.Add("Unsupported formatting check: $id; only CHAR-001 is allowed.") }
    }
    Write-Stage "Specification validation complete; $($configurationErrors.Count) configuration error(s)."
    return @($spec.checks)
}
try {
    Write-Stage 'Comparison engine started.'
    Write-Stage 'Resolving input paths.'
    $TemplatePath = (Resolve-Path -LiteralPath $TemplatePath).Path
    $DocumentPath = (Resolve-Path -LiteralPath $DocumentPath).Path
    if ($TemplatePath -ieq $DocumentPath) { throw 'Template and target must be different files.' }
    if ([IO.Path]::GetExtension($DocumentPath) -ine '.docx' -or @('.docx','.dotx') -notcontains [IO.Path]::GetExtension($TemplatePath).ToLowerInvariant()) {
        throw 'The target must be .docx and the template must be .dotx or .docx.'
    }
    $folder = Split-Path -Parent $DocumentPath
    $stem = [IO.Path]::GetFileNameWithoutExtension($DocumentPath)
    $output = Join-Path $folder ($stem + '-HIGHLIGHT.docx')
    $activityDocument = Join-Path $folder 'activity.docx'
    # FR-004: Insert -HIGHLIGHT before the source document extension.
    # FR-006: Neither the highlighted copy nor activity.docx may overwrite an earlier output.
    if ((Test-Path -LiteralPath $output) -or (Test-Path -LiteralPath $activityDocument)) {
        throw 'An output already exists. Rename or move the previous highlighted document and activity.docx before running again.'
    }
    $checks = @(Load-CheckSpecification $SpecificationPath)
    Write-Stage 'Starting Microsoft Word COM automation.'
    $word = New-Object -ComObject Word.Application
    Write-Stage 'Microsoft Word COM automation started.'
    $word.Visible = $false
    $word.DisplayAlerts = 0
    Write-Stage 'Word configured for hidden execution.'
    if ($configurationErrors.Count -gt 0) {
        Write-Stage 'Invalid specification detected; preparing activity.docx.'
        Write-ActivityDocument $configurationErrors $findings $activityDocument $TemplatePath $DocumentPath
        throw "Format-check specification contains $($configurationErrors.Count) error(s). See $activityDocument"
    }
    Write-Stage 'Copying target document for comparison.'
    Copy-Item -LiteralPath $DocumentPath -Destination $output
    Write-Stage 'Opening reference document in Word.'
    $reference = $word.Documents.Open($TemplatePath, $false, $true)
    Write-Stage 'Opening target document in Word.'
    $target = $word.Documents.Open($output, $false, $false)
    Write-Stage 'Both documents opened; beginning comparison.'
    $rp = $reference.Paragraphs
    $tp = $target.Paragraphs
    $referenceParagraphCount = [int]$rp.Count
    $targetParagraphCount = [int]$tp.Count
    $totalParagraphs = [Math]::Max($referenceParagraphCount,$targetParagraphCount)
    $comparisonStartedUtc = [DateTime]::UtcNow
    $comparisonOutcome = 'In progress'
    $comparisonTimer = [Diagnostics.Stopwatch]::StartNew()
    $nextProgressTime = [DateTime]::UtcNow.AddSeconds(5)
    Write-Stage "Comparing $totalParagraphs paragraph(s); timeout $ComparisonTimeoutSeconds seconds. Press Esc to cancel."
    # FR-004, FR-009: Compare formatting positionally and report structural mismatches.
    for ($i=1; $i -le $totalParagraphs; $i++) {
        Test-UserCancellation
        if ($comparisonTimer.Elapsed.TotalSeconds -ge $ComparisonTimeoutSeconds) {
            throw "Comparison exceeded $ComparisonTimeoutSeconds seconds at paragraph $i of $totalParagraphs."
        }
        if ($i -eq 1 -or $i -eq $totalParagraphs -or [DateTime]::UtcNow -ge $nextProgressTime) {
            Write-Stage ("Comparing paragraph {0}/{1}; elapsed {2:n1}s; findings {3}; errors {4}." -f $i,$totalParagraphs,$comparisonTimer.Elapsed.TotalSeconds,$findings.Count,$configurationErrors.Count)
            $nextProgressTime = [DateTime]::UtcNow.AddSeconds(5)
        }
        $processedParagraphs = $i
        if ($i -gt $targetParagraphCount) {
            $findings.Add("Paragraph $i is missing in target.")
            $changedParagraphs.Add([pscustomobject]@{Number=$i; Text='[Missing in target]'; Marked=@($true)})
            continue
        }
        $t = $tp.Item($i)
        if ($i -gt $referenceParagraphCount) {
            Highlight $t.Range
            $text = $t.Range.Text.TrimEnd([char]13,[char]7)
            $changedParagraphs.Add([pscustomobject]@{Number=$i; Text=$text; Marked=@($true) * [Math]::Max(1,$text.Length)})
            $findings.Add("Paragraph $i exists only in target.")
            continue
        }
        $r = $rp.Item($i)
        $tt = $t.Range.Text.TrimEnd([char]13,[char]7)
        $rt = $r.Range.Text.TrimEnd([char]13,[char]7)
        $marks = New-Object 'bool[]' $tt.Length
        $paragraphChanged = $false
        if ($tt -cne $rt) {
            Highlight $t.Range
            for ($k=0; $k -lt $marks.Length; $k++) { $marks[$k] = $true }
            $paragraphChanged = $true
            $findings.Add("Paragraph $i text differs from the corresponding template paragraph.")
            # Structural text reporting is retained; font comparison remains style-based.
        }
        # CHAR-001: non-positional comparison against the matching template style.
        # A definite uniform paragraph font equal to the style font is a fast PASS.
        foreach ($check in $checks) {
            Test-UserCancellation
            if ($comparisonTimer.Elapsed.TotalSeconds -ge $ComparisonTimeoutSeconds) {
                throw "Comparison exceeded $ComparisonTimeoutSeconds seconds at paragraph $i of $totalParagraphs."
            }
            if ($check.enabled -ne $true) { continue }
            try {
                $expectedFont = Get-StyleFontProperties $reference $t
                # All four properties must be uniformly correct for the fast path.
                if (Test-FontProperties $t.Range.Font $expectedFont) { continue }
                for ($j=1; $j -le $tt.Length; $j++) {
                    if (($j % 100) -eq 1) {
                        Test-UserCancellation
                        if ($comparisonTimer.Elapsed.TotalSeconds -ge $ComparisonTimeoutSeconds) {
                            throw "Comparison exceeded $ComparisonTimeoutSeconds seconds at paragraph $i character $j."
                        }
                    }
                    $character = $t.Range.Characters.Item($j)
                    if (-not (Test-FontProperties $character.Font $expectedFont)) {
                        Highlight $character
                        $marks[$j - 1] = $true
                        $paragraphChanged = $true
                    }
                }
            } catch {
                if ($_.Exception -is [System.OperationCanceledException] -or $_.Exception.Message -like "Comparison exceeded $ComparisonTimeoutSeconds seconds*") { throw }
                $configurationErrors.Add("Formatting comparison failed: check $($check.id), paragraph $i, attempted font family, size, bold and italic against corresponding template style. Reason: $($_.Exception.Message)")
            }
        }
        if ($paragraphChanged) {
            $changedParagraphs.Add([pscustomobject]@{Number=$i; Text=$tt; Marked=$marks})
            $findings.Add("Paragraph $i has formatting differences.")
        }
    }
    $comparisonTimer.Stop()
    $comparisonFinishedUtc = [DateTime]::UtcNow
    $comparisonOutcome = if ($configurationErrors.Count -eq 0) { 'Completed' } else { 'Completed with errors' }
    Write-Stage ("Comparison finished in {0:n1}s; findings {1}; errors {2}." -f $comparisonTimer.Elapsed.TotalSeconds,$findings.Count,$configurationErrors.Count)
    if ($configurationErrors.Count -gt 0) {
        $target.Close($false); $target = $null
        Write-ActivityDocument $configurationErrors $findings $activityDocument $TemplatePath $DocumentPath
        throw "One or more configured checks could not be executed. See $activityDocument"
    }
    Write-Stage 'Saving highlighted comparison document.'
    $target.Save()
    Write-Stage 'Writing activity report.'
    Write-ActivityDocument $configurationErrors $findings $activityDocument $TemplatePath $DocumentPath
    Write-Host "Highlighted copy: $output"
    Write-Host "Activity report: $activityDocument"
    Write-Host "Findings: $($findings.Count)"

} catch {
    if ($null -ne $comparisonTimer -and $comparisonTimer.IsRunning) { $comparisonTimer.Stop() }
    if ($null -ne $comparisonStartedUtc -and $null -eq $comparisonFinishedUtc) { $comparisonFinishedUtc = [DateTime]::UtcNow }
    if ($comparisonOutcome -eq 'In progress') {
        $comparisonOutcome = if ($_.Exception -is [System.OperationCanceledException]) { 'Cancelled' } else { 'Failed' }
    }
    if ($null -ne $activityDocument -and -not (Test-Path -LiteralPath $activityDocument)) {
        $configurationErrors.Add("Comparison could not be completed: $($_.Exception.Message)")
        try { Write-ActivityDocument $configurationErrors $findings $activityDocument $TemplatePath $DocumentPath }
        catch { Write-Stage "Unable to write activity report: $($_.Exception.Message)" }
    }
    Write-Stage "Engine error: $($_.Exception.Message)"
    Write-Error $_
    exit 1
} finally {
    Write-Stage 'Releasing Word documents and COM automation.'
    if ($null -ne $target) { try { $target.Close($false) } catch {} }
    if ($null -ne $reference) { try { $reference.Close($false) } catch {} }
    if ($null -ne $word) { try { $word.Quit() } catch {} }
    foreach ($obj in @($target,$reference,$word)) {
        if ($null -ne $obj -and [Runtime.InteropServices.Marshal]::IsComObject($obj)) {
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($obj)
        }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
