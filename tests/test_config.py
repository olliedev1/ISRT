"""
Unit tests for the configuration module (isrt/config.py).
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import isrt.config as cfg


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    """Redirect config file to a temporary directory for each test."""
    config_dir = tmp_path / ".isrt"
    config_file = config_dir / "config.json"
    with patch.object(cfg, "CONFIG_DIR", config_dir), patch.object(
        cfg, "CONFIG_FILE", config_file
    ):
        yield config_dir, config_file


class TestListProfiles:
    def test_empty_when_no_file(self):
        assert cfg.list_profiles() == {}

    def test_returns_saved_profiles(self):
        cfg.save_profile("srv1", "10.0.0.1", 27015, "pass1")
        profiles = cfg.list_profiles()
        assert "srv1" in profiles


class TestSaveAndGetProfile:
    def test_save_and_retrieve(self):
        cfg.save_profile("prod", "1.2.3.4", 27020, "secret", timeout=15.0)
        profile = cfg.get_profile("prod")
        assert profile is not None
        assert profile["host"] == "1.2.3.4"
        assert profile["port"] == 27020
        assert profile["password"] == "secret"
        assert profile["timeout"] == 15.0

    def test_get_nonexistent_returns_none(self):
        assert cfg.get_profile("ghost") is None

    def test_overwrite_profile(self):
        cfg.save_profile("srv", "1.1.1.1", 27015, "old")
        cfg.save_profile("srv", "2.2.2.2", 27016, "new")
        profile = cfg.get_profile("srv")
        assert profile["host"] == "2.2.2.2"
        assert profile["password"] == "new"


class TestDeleteProfile:
    def test_delete_existing(self):
        cfg.save_profile("temp", "1.1.1.1", 27015, "pw")
        assert cfg.delete_profile("temp") is True
        assert cfg.get_profile("temp") is None

    def test_delete_nonexistent_returns_false(self):
        assert cfg.delete_profile("ghost") is False


class TestDefaultProfile:
    def test_no_default_initially(self):
        assert cfg.get_default_profile() is None

    def test_set_and_get_default(self):
        cfg.save_profile("main", "1.1.1.1", 27015, "pw")
        cfg.set_default_profile("main")
        assert cfg.get_default_profile() == "main"

    def test_change_default(self):
        cfg.save_profile("a", "1.1.1.1", 27015, "pw")
        cfg.save_profile("b", "2.2.2.2", 27015, "pw")
        cfg.set_default_profile("a")
        cfg.set_default_profile("b")
        assert cfg.get_default_profile() == "b"


class TestPersistence:
    def test_data_persists_across_calls(self, isolated_config):
        _, config_file = isolated_config
        cfg.save_profile("persist", "9.9.9.9", 27015, "pw")
        # Re-read from file directly
        with config_file.open() as f:
            data = json.load(f)
        assert "persist" in data["profiles"]

    def test_corrupt_config_returns_empty(self, isolated_config):
        _, config_file = isolated_config
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("NOT VALID JSON")
        assert cfg.list_profiles() == {}
