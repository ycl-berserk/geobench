# Build the Windows release folder and zip it.
#
# One folder, not one file: it starts faster and antivirus software is
# less suspicious of it.  Run from PowerShell:
#
#     .\packaging\build.ps1
#
# The result is dist\geobench\ (the folder) and dist\geobench-win64.zip.

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$python = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} else {
    "python"
}

& $python -m pip install --upgrade "pyinstaller>=6.6"
& $python scripts/make_icon.py
& $python -m PyInstaller --noconfirm packaging/geobench.spec

Copy-Item samples dist/geobench -Recurse -Force
Copy-Item docs/teacher-guide.md "dist/geobench/使用说明.md" -Force
Copy-Item LICENSE dist/geobench/LICENSE -Force

Compress-Archive -Path dist/geobench -DestinationPath dist/geobench-win64.zip -Force
Write-Host "built dist/geobench-win64.zip"
