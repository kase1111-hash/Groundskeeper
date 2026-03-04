"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

from groundskeeper.core.config import load_thresholds, load_trusted_apps


class TestLoadThresholds:
    def test_loads_from_bundled_config(self):
        config = load_thresholds()
        assert config.dormancy_days == 90
        assert config.phantom_cycle_hours == 24
        assert config.max_blanket_repos == 5
        assert config.overprovision_lookback_days == 30

    def test_falls_back_to_defaults_if_missing(self, tmp_path: Path):
        config = load_thresholds(config_dir=tmp_path)
        assert config.dormancy_days == 90

    def test_loads_custom_values(self, tmp_path: Path):
        thresholds_file = tmp_path / "thresholds.yaml"
        thresholds_file.write_text("dormancy_days: 30\nmax_blanket_repos: 20\n")
        config = load_thresholds(config_dir=tmp_path)
        assert config.dormancy_days == 30
        assert config.max_blanket_repos == 20
        # Unspecified values keep defaults
        assert config.phantom_cycle_hours == 24


class TestLoadTrustedApps:
    def test_loads_from_bundled_config(self):
        config = load_trusted_apps()
        assert config.is_trusted("github", "anthropics") is True
        assert config.is_trusted("github", "github") is True
        assert config.is_trusted("google", "google.com") is True

    def test_falls_back_to_empty_if_missing(self, tmp_path: Path):
        config = load_trusted_apps(config_dir=tmp_path)
        assert config.is_trusted("github", "anyone") is False

    def test_loads_custom_entries(self, tmp_path: Path):
        trusted_file = tmp_path / "trusted_apps.yaml"
        trusted_file.write_text(
            "trusted:\n"
            "  github:\n"
            "    - developer: my-org\n"
            "  custom:\n"
            "    - developer: custom-dev\n"
        )
        config = load_trusted_apps(config_dir=tmp_path)
        assert config.is_trusted("github", "my-org") is True
        assert config.is_trusted("custom", "custom-dev") is True
        assert config.is_trusted("github", "anthropics") is False
