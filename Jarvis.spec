from PyInstaller.utils.hooks import collect_data_files, collect_submodules

piper_data = collect_data_files("piper")

hiddenimports = (
    collect_submodules("Automation")
    + collect_submodules("Brain")
    + collect_submodules("Features")
    + collect_submodules("selenium.webdriver.chrome")
    + [
        "piper",
        "piper.voice",
        "piper.config",
        "piper.const",
        "piper.phoneme_ids",
        "piper.phonemize_espeak",
        "piper.tashkeel",
        "onnxruntime",
    ]
)

analysis = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=piper_data + [
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
