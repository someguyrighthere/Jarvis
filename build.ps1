$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
$python = "py"

& $python -3.12 -m pip install --upgrade pyinstaller
& $python -3.12 -m PyInstaller --noconfirm --clean .\Jarvis.spec

New-Item -ItemType Directory -Force -Path .\dist\JarvisPackage | Out-Null
Copy-Item .\dist\Jarvis.exe .\dist\JarvisPackage\Jarvis.exe -Force
foreach ($file in @("Alam_data.txt", "input.txt", "log.txt", "schedule.txt", "voice_state.txt")) {
    Copy-Item ".\$file" ".\dist\JarvisPackage\$file" -Force
}

Write-Host "Package created at $((Resolve-Path .\dist\JarvisPackage).Path)"
