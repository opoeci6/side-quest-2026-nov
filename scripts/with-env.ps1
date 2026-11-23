# Run one command with the project-local toolchain: .venv first on PATH,
# caches under .cache\. Nothing is installed or configured system-wide.
# Usage: scripts/with-env.ps1 <command> [args...]
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$VenvBin = Join-Path $Root '.venv\Scripts'
if (-not (Test-Path $VenvBin)) {
    Write-Error 'with-env: no .venv found. Create it first: python -m venv .venv (see docs/dev-setup.md)'
}

$env:VIRTUAL_ENV = Join-Path $Root '.venv'
$env:PATH = "$VenvBin;$(Join-Path $Root '.tools\bin');$(Join-Path $Root '.tools');$env:PATH"
$env:PIP_CACHE_DIR = Join-Path $Root '.cache\pip'
$env:XDG_CACHE_HOME = Join-Path $Root '.cache'
$env:PYTHONUTF8 = '1'
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'

if ($args.Count -eq 0) {
    Write-Error 'usage: scripts/with-env.ps1 <command> [args...]'
}
$cmd = $args[0]
$rest = @()
if ($args.Count -gt 1) { $rest = $args[1..($args.Count - 1)] }
& $cmd @rest
exit $LASTEXITCODE
