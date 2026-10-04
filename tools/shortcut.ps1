param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Python)
$ErrorActionPreference = 'Stop'
$matrixDesktop = [Environment]::GetFolderPath('Desktop')
$matrixTarget = Join-Path $matrixDesktop 'Agent Matrix.lnk'
if (Test-Path -LiteralPath $matrixTarget) { throw 'Existing Agent Matrix shortcut preserved.' }
$matrixShell = New-Object -ComObject WScript.Shell
$matrixLink = $matrixShell.CreateShortcut($matrixTarget)
$matrixLink.TargetPath = $Python
$matrixLink.Arguments = '"' + (Join-Path $Root 'host\launch.py') + '"'
$matrixLink.WorkingDirectory = $Root
$matrixLink.Description = 'Open Agent Matrix status display'
$matrixLink.Save()
Write-Output $matrixTarget
