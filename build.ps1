$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot 'build\pyinstaller-cache'
$env:MPLCONFIGDIR = Join-Path $PSScriptRoot 'build\mpl-cache'
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --workpath build/work --windowed --onedir --name CausalStudio --collect-all causallearn --collect-all tigramite --collect-all lingam --collect-all dcor --copy-metadata causal-learn --copy-metadata tigramite --copy-metadata lingam --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module IPython --exclude-module pytest --exclude-module __main__ launch.py
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
& '.\.venv\Scripts\python.exe' finalize_bundle.py
if ($LASTEXITCODE -ne 0) { throw 'Bundle finalization failed.' }
Write-Host 'Built: dist\CausalStudio\CausalStudio.exe'
