<#
Runs one conservative, cache-aware publication-image sync. Python is the only
JSON reader: discovery-cache.json can preserve JSON keys differing only by
case, which PowerShell ConvertFrom-Json cannot represent.
#>
[CmdletBinding()]
param([string]$TaskName = "")

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Assets = Join-Path $ProjectRoot "assets\publications"
$ReportPath = Join-Path $Assets "image-sync-final-report.md"
$Now = [DateTimeOffset]::UtcNow
$lines = [System.Collections.Generic.List[string]]::new()
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"

function Add-Report([string]$Text) { [void]$lines.Add($Text) }

try {
    Set-Location -LiteralPath $ProjectRoot
    $preflight = & python -c "import json; from pathlib import Path; p=json.loads(Path('publications.json').read_text(encoding='utf-8')); assert len(p)==37, f'expected 37 publications, found {len(p)}'; print('preflight: 37 publications; JSON valid')" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Python preflight failed: $preflight" }

    Add-Report "# Publication image sync report"
    Add-Report ""
    Add-Report "- Executed (UTC): $($Now.ToString('u'))"
    Add-Report "- Scope: current publications.json only (37 records)"
    Add-Report "- Cache parsing and retry-after decisions: Python discovery tool only"
    Add-Report ""
    Add-Report "## Preflight"
    Add-Report '```text'
    foreach ($line in $preflight) { Add-Report ([string]$line) }
    Add-Report '```'

    # The discovery client checks retry_after per source. Expired sources are
    # retried at its low rate; sources still deferred are not probed.
    $discoveryOutput = & python -u scripts\discover_publication_images.py --delay 0.5 2>&1
    $discoveryExit = $LASTEXITCODE
    Add-Report ""
    Add-Report "## Discovery"
    Add-Report '```text'
    foreach ($line in $discoveryOutput) { Add-Report ([string]$line) }
    Add-Report '```'
    Add-Report "Exit code: $discoveryExit"
    if ($discoveryExit -ne 0) { throw "Discovery failed with exit code $discoveryExit" }

    # Importer rejects every candidate except an explicit HTTPS direct image
    # with a confirmed CC0, Public Domain, or CC BY licence.
    $importOutput = & python -u scripts\import_publication_images.py --candidates assets\publications\candidates.json --apply 2>&1
    $importExit = $LASTEXITCODE
    Add-Report ""
    Add-Report "## Import"
    Add-Report '```text'
    foreach ($line in $importOutput) { Add-Report ([string]$line) }
    Add-Report '```'
    Add-Report "Exit code: $importExit"
    if ($importExit -ne 0) { throw "Importer failed with exit code $importExit" }

    # Python validates the frontend resolution contract without changing data:
    # verified local image -> HTTPS legacy image -> default SVG.
    $validationCode = @'
import json, re
from pathlib import Path
from urllib.parse import urlparse
root = Path('.')
assets = root / 'assets' / 'publications'
publications = json.loads((root / 'publications.json').read_text(encoding='utf-8'))
candidates = json.loads((assets / 'candidates.json').read_text(encoding='utf-8'))
manual = json.loads((assets / 'manual-image-review.json').read_text(encoding='utf-8'))
cache = json.loads((assets / 'discovery-cache.json').read_text(encoding='utf-8'))
assert len(publications) == 37
assert len(manual.get('manual_review', [])) == 37
def safe_local(value):
    return isinstance(value, str) and re.fullmatch(r'assets/publications/[A-Za-z0-9][A-Za-z0-9._/-]*\.(svg|png|jpe?g|webp|gif)', value, re.I) and '..' not in value
def safe_https(value):
    parsed = urlparse(value) if isinstance(value, str) else None
    return bool(parsed and parsed.scheme == 'https' and parsed.netloc and not any(ch.isspace() for ch in value))
counts = {'local': 0, 'https': 0, 'default': 0}
missing = []
for publication in publications:
    image = publication.get('image') if isinstance(publication.get('image'), dict) else {}
    local = image.get('path') if image.get('status') == 'verified' else None
    legacy = publication.get('img_scr')
    legacy = legacy[0] if isinstance(legacy, list) and legacy else None
    if safe_local(local):
        counts['local'] += 1
        if not (root / local).is_file(): missing.append(local)
    elif safe_https(legacy):
        counts['https'] += 1
    else:
        counts['default'] += 1
assert not missing
assert sum(counts.values()) == 37
assert (assets / 'default-cover.svg').is_file()
print(json.dumps({'json_valid': True, 'publication_cards': 37, 'image_sources': counts, 'empty_src': 0, 'missing_local_assets': missing, 'candidate_summary': candidates.get('summary', {}), 'manual_review_entries': len(manual['manual_review']), 'deferred_sources': cache.get('blocked_reasons', {})}, ensure_ascii=False))
'@
    $validationOutput = $validationCode | & python - 2>&1
    $validationExit = $LASTEXITCODE
    Add-Report ""
    Add-Report "## Validation"
    Add-Report '```json'
    foreach ($line in $validationOutput) { Add-Report ([string]$line) }
    Add-Report '```'
    Add-Report "Exit code: $validationExit"
    if ($validationExit -ne 0) { throw "Final validation failed with exit code $validationExit" }
}
catch {
    Add-Report ""
    Add-Report "## Failure"
    Add-Report $_.Exception.Message
    throw
}
finally {
    $lines | Set-Content -LiteralPath $ReportPath -Encoding utf8
    if ($TaskName) { schtasks.exe /Delete /TN $TaskName /F *> $null }
}
