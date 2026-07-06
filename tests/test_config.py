"""Tests for config deep-merge and environment overrides."""
import os
from pathlib import Path

import yaml

from config import Config, DEFAULT_CONFIG


def test_deep_merge_preserves_defaults(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"news": {"enabled": False}}))

    cfg = Config(config_file)
    assert cfg.get("news", "enabled") is False
    assert cfg.get("news", "interval_minutes") == DEFAULT_CONFIG["news"]["interval_minutes"]
    assert cfg.get("playback", "volume") == DEFAULT_CONFIG["playback"]["volume"]


def test_env_override_bool(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({}))
    monkeypatch.setenv("NEWS_ENABLED", "false")

    cfg = Config(config_file)
    assert cfg.get("news", "enabled") is False


def test_env_override_list(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({}))
    monkeypatch.setenv("NEWS_FEEDS", "bbc,cnn")

    cfg = Config(config_file)
    assert cfg.get("news", "feeds") == ["bbc", "cnn"]
