"""Path utilities that work in both dev and PyInstaller exe contexts."""
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """Get the base directory of the application.

    Works in both:
    - Dev: returns the directory containing this script
    - PyInstaller exe: returns the _internal directory in the exe folder
    """
    if getattr(sys, 'frozen', False):
        # Running from PyInstaller exe
        return Path(sys.executable).parent / "_internal"
    else:
        # Running from Python script
        return Path(__file__).parent


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
DJ_IMAGES_DIR = DATA_DIR / "dj_images"
DB_PATH = DATA_DIR / "ai_dj.db"
TTS_CACHE_DIR = DATA_DIR / "tts_cache"
CONFIG_PATH = BASE_DIR / "config.yaml"


# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)
DJ_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
