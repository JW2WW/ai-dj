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
        return Path(sys.executable).parent / "_internal"
    return Path(__file__).parent


def get_exe_dir() -> Path:
    """Get the directory containing the executable (or script in dev mode).

    This is where users place config.yaml, .env, and runtime data/."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = get_base_dir()
EXE_DIR = get_exe_dir()
CONFIG_PATH = EXE_DIR / "config.yaml"
DATA_DIR = EXE_DIR / "data"
DJ_IMAGES_DIR = DATA_DIR / "dj_images"
DB_PATH = DATA_DIR / "ai_dj.db"
TTS_CACHE_DIR = DATA_DIR / "tts_cache"
ARTIST_IMAGES_DIR = DATA_DIR / "artist_images"
ASSETS_DIR = BASE_DIR / "assets"
DEFAULT_DJ_IMAGES_DIR = ASSETS_DIR / "dj_images"

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DJ_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def resolve_dj_image(image_path: str | None) -> Path | None:
    """Resolve a DJ image path, checking user-uploaded then bundled defaults.

    Priority:
    1. Absolute path (legacy) — used as-is if the file exists
    2. DJ_IMAGES_DIR / filename — user-uploaded image
    3. DEFAULT_DJ_IMAGES_DIR / filename — bundled default image

    Returns the resolved Path, or None if nothing exists.
    """
    if not image_path:
        return None

    # Absolute path (legacy)
    p = Path(image_path)
    if p.is_absolute():
        return p if p.exists() else None

    # User-uploaded image (data/dj_images/<filename>)
    user_path = DJ_IMAGES_DIR / image_path
    if user_path.exists():
        return user_path

    # Bundled default (assets/dj_images/<filename>)
    default_path = DEFAULT_DJ_IMAGES_DIR / image_path
    if default_path.exists():
        return default_path

    return None
