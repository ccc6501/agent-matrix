[CmdletBinding()]
param(
    [ValidateSet('codex','claude','opencode','cline','none')][string[]]$Agents,
    [switch]$NoShortcut,
    [switch]$SkipBoard
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
    & py -3 -m venv .venv
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
    & python -m venv .venv
}
else { throw 'Install Python 3.12 or newer from python.org, then run setup again.' }
if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
$matrixPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $matrixPython -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$matrixArgs = @('tools\manage.py', 'install')
if ($Agents) { $matrixArgs += @('--agents', ($Agents -join ',')) }
if ($NoShortcut) { $matrixArgs += '--no-shortcut' }
if ($SkipBoard) { $matrixArgs += '--skip-board' }
& $matrixPython @matrixArgs
if ($LASTEXITCODE -ne 0) { throw 'Agent Matrix setup did not finish. See the message above.' }
