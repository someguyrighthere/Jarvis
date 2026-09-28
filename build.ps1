param(
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
$projectVenvPython = Join-Path $PSScriptRoot ".venv312\Scripts\python.exe"
$venvPython = Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"
if ($PythonExecutable -and -not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw "The requested Python executable was not found: $PythonExecutable"
}
$python = if ($PythonExecutable) { $PythonExecutable } elseif (Test-Path $projectVenvPython) { $projectVenvPython } elseif (Test-Path $venvPython) { $venvPython } else { "python" }

# Remove any installer left over from a previous build so a stale, wrong-version
# executable can never be picked up by the packaging or release steps.
if (Test-Path .\dist\installer) {
    Remove-Item -Path .\dist\installer -Recurse -Force
}

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
& $python -m pip install -r .\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install project requirements." }
& $python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller." }
$pyinstallerRoot = Join-Path $env:TEMP ("Jarvis-PyInstaller-" + [guid]::NewGuid().ToString("N"))
$pyinstallerWork = Join-Path $pyinstallerRoot "build"
$pyinstallerDist = Join-Path $pyinstallerRoot "dist"
& $python -m PyInstaller --noconfirm --clean --workpath $pyinstallerWork --distpath $pyinstallerDist .\Jarvis.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed; refusing to package a stale executable." }

New-Item -ItemType Directory -Force -Path .\dist\JarvisPackage | Out-Null
Copy-Item (Join-Path $pyinstallerDist "Jarvis.exe") .\dist\Jarvis.exe -Force
Copy-Item .\dist\Jarvis.exe .\dist\JarvisPackage\Jarvis.exe -Force
foreach ($file in @("Alam_data.txt", "input.txt", "log.txt", "schedule.txt", "voice_state.txt")) {
    if (Test-Path ".\$file") {
        Copy-Item ".\$file" ".\dist\JarvisPackage\$file" -Force
    } elseif ($file -eq "voice_state.txt") {
        Set-Content ".\dist\JarvisPackage\$file" "IDLE" -NoNewline
    }
}

Write-Host "Package created at $((Resolve-Path .\dist\JarvisPackage).Path)"
