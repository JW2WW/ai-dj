"""Configuration management: YAML-based settings with environment overrides."""
import os
from pathlib import Path

import yaml

from paths import CONFIG_PATH

DEFAULT_CONFIG = {
    "playback": {
        "volume": 80,
    },
    "commentary": {
        "enabled": True,
        "target_seconds": 18,
        "cache": True,
    },
    "news": {
        "enabled": True,
        "interval_minutes": 30,
        "target_seconds": 15,
        "feeds": ["npr", "ycombinator"],
        "after_every_song": False,  # Play a news brief after every song (great for testing)
    },
    "market": {
        "enabled": True,
        "time": "16:00",
        "target_seconds": 12,
        "tickers": ["^GSPC", "^IXIC", "^DJI", "GLD", "^VIX"],
    },
        "weather": {
            "enabled": True,
            "time_between_songs": True,
            "city": None,  # e.g., "Kansas City"
            "zip_code": None,  # e.g., "64108"
            "play_every_n_songs": 3,
        },
    "tts": {
        "voice": "en-US-AriaNeural",
        "cache": True,
    },
    "llm": {
        "primary": "gemini",
        "fallback": "groq",
        "gemini_model": "gemini-2.5-flash",
        "groq_model": "llama-3.3-70b-versatile",
    },
    "logging": {
        "verbose": False,
    },
}


class Config:
    def __init__(self, config_file: Path | None = None):
        self.config_file = config_file or CONFIG_PATH
        self.data = self._load()

    def _load(self) -> dict:
        """Load config from YAML file, or use defaults if missing."""
        if self.config_file.exists():
            with open(self.config_file) as f:
                user_config = yaml.safe_load(f) or {}
        else:
            user_config = {}

        # Merge user config with defaults (user config takes precedence)
        merged = self._deep_merge(DEFAULT_CONFIG, user_config)
        # Environment variable overrides (e.g., COMMENTARY_TARGET_SECONDS=20)
        self._apply_env_overrides(merged)
        return merged

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override into base, preserving base keys not in override."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _apply_env_overrides(config: dict) -> None:
        """Apply environment variable overrides using SECTION_KEY=value pattern."""
        for section, settings in config.items():
            if isinstance(settings, dict):
                for key, default in settings.items():
                    env_key = f"{section.upper()}_{key.upper()}"
                    env_val = os.getenv(env_key)
                    if env_val is not None:
                        # Coerce to type of default (bool, int, str, list)
                        if isinstance(default, bool):
                            config[section][key] = env_val.lower() in ("true", "1", "yes")
                        elif isinstance(default, int):
                            config[section][key] = int(env_val)
                        elif isinstance(default, list):
                            config[section][key] = [s.strip() for s in env_val.split(",")]
                        else:
                            config[section][key] = env_val

    def get(self, section: str, key: str, default=None):
        """Get a config value with fallback to default."""
        return self.data.get(section, {}).get(key, default)

    def __getitem__(self, section: str) -> dict:
        """Access config sections like config["commentary"]."""
        return self.data.get(section, {})

    def save(self, path: Path | None = None) -> None:
        """Save current config to YAML file."""
        path = path or self.config_file
        with open(path, "w") as f:
            yaml.dump(self.data, f, default_flow_style=False)

    def __repr__(self) -> str:
        return f"Config({self.config_file})"


# Global singleton
_global_config = None


def get_config() -> Config:
    """Get the global config instance (lazy singleton)."""
    global _global_config
    if _global_config is None:
        _global_config = Config()
    return _global_config


if __name__ == "__main__":
    cfg = Config()
    print("Current config:")
    for section, settings in cfg.data.items():
        print(f"  [{section}]")
        for key, val in settings.items():
            print(f"    {key}: {val}")
    print()
    print("Example overrides via environment:")
    print("  COMMENTARY_TARGET_SECONDS=25")
    print("  NEWS_ENABLED=false")
    print("  PLAYBACK_VOLUME=60")
