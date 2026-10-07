import argparse
import shutil
from pathlib import Path

from TextToSpeech.Fast_DF_TTS import (
    PIPER_CONFIG_NAME,
    PIPER_MODEL_NAME,
    _download_piper_file,
)


def prepare_voice(package_root: Path) -> None:
    destination = package_root / "models" / "piper"
    destination.mkdir(parents=True, exist_ok=True)
    for filename, limit in [(PIPER_MODEL_NAME, 150 * 1024 * 1024),
                            (PIPER_CONFIG_NAME, 1024 * 1024)]:
        source = _download_piper_file(filename, limit)
        shutil.copy2(source, destination / filename)
    shutil.copy2(Path(__file__).with_name("PIPER-VOICE-NOTICE.txt"), destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage the offline Piper voice for SARA's installer.")
    parser.add_argument("package_root", type=Path)
    prepare_voice(parser.parse_args().package_root)
