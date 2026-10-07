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
        ("avatar_web/index.html", "avatar_web"),
        ("avatar_web/avatar.js", "avatar_web"),
        ("avatar_web/speech_motion.mjs", "avatar_web"),
        ("avatar_web/updates.js", "avatar_web"),
        ("avatar_web/dependencies.js", "avatar_web"),
        ("avatar_web/assistant.js", "avatar_web"),
        ("avatar_web/memory.js", "avatar_web"),
        ("avatar_web/action_history.js", "avatar_web"),
        ("requirements.txt", "."),
        ("avatar_web/node_modules/three/build", "avatar_web/node_modules/three/build"),
        ("avatar_web/node_modules/three/examples/jsm", "avatar_web/node_modules/three/examples/jsm"),
        ("avatar_web/node_modules/three/LICENSE", "avatar_web/node_modules/three"),
        ("assets/avatars/business-female-01", "assets/avatars/business-female-01"),
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
    icon="sara.ico",
)
