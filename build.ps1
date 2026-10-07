param(
    [string]$PythonExecutable,
    [switch]$SkipDependencyInstall
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

if (-not $SkipDependencyInstall) {
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
    & $python -m pip install -r .\requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Failed to install project requirements." }
    & $python -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller." }
    & npm.cmd --prefix .\avatar_web ci
    if ($LASTEXITCODE -ne 0) { throw "Failed to prepare the bundled avatar renderer." }
}
& $python -B .\prepare_installer.py .\dist\JarvisPackage
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare the bundled offline voice." }
$webviewBootstrapper = Join-Path $PSScriptRoot "dist\JarvisPackage\MicrosoftEdgeWebview2Setup.exe"
Invoke-WebRequest -UseBasicParsing -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $webviewBootstrapper
$signature = Get-AuthenticodeSignature -LiteralPath $webviewBootstrapper
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") {
    throw "The WebView2 bootstrapper does not have a valid Microsoft signature."
}
$pyinstallerRoot = Join-Path $env:TEMP ("Jarvis-PyInstaller-" + [guid]::NewGuid().ToString("N"))
$pyinstallerWork = Join-Path $pyinstallerRoot "build"
$pyinstallerDist = Join-Path $pyinstallerRoot "dist"
& $python -m PyInstaller --noconfirm --clean --workpath $pyinstallerWork --distpath $pyinstallerDist .\Jarvis.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed; refusing to package a stale executable." }

New-Item -ItemType Directory -Force -Path .\dist\JarvisPackage | Out-Null
Copy-Item (Join-Path $pyinstallerDist "Jarvis.exe") .\dist\Jarvis.exe -Force
Copy-Item .\dist\Jarvis.exe .\dist\JarvisPackage\Jarvis.exe -Force
Copy-Item .\sara.ico .\dist\JarvisPackage\sara.ico -Force
foreach ($file in @("Alam_data.txt", "input.txt", "log.txt", "schedule.txt", "voice_state.txt")) {
    $initialState = if ($file -eq "voice_state.txt") { "IDLE" } else { "" }
    Set-Content ".\dist\JarvisPackage\$file" $initialState -NoNewline
}

Write-Host "Package created at $((Resolve-Path .\dist\JarvisPackage).Path)"
