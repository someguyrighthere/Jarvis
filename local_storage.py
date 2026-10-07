import os
import sys
from pathlib import Path


LOCAL_APP_DATA = Path(
    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
)
LOCAL_DATA_DIR = LOCAL_APP_DATA / "Sara"
LEGACY_DATA_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
