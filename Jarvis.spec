from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("Automation") + collect_submodules("Brain") + collect_submodules("Features")

analysis = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("Alam_data.txt", "."),
        ("input.txt", "."),
        ("log.txt", "."),
        ("schedule.txt", "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
