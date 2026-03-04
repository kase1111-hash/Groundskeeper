"""Configuration loading for thresholds and trusted apps."""

from __future__ import annotations

from pathlib import Path

import yaml

from groundskeeper.core.models import ThresholdConfig, TrustedAppsConfig, TrustedDeveloper

_DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_thresholds(config_dir: Path | None = None) -> ThresholdConfig:
    """Load threshold configuration from YAML, falling back to defaults."""
    path = (config_dir or _DEFAULT_CONFIG_DIR) / "thresholds.yaml"
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return ThresholdConfig(**data)
    return ThresholdConfig()


def load_trusted_apps(config_dir: Path | None = None) -> TrustedAppsConfig:
    """Load trusted apps configuration from YAML, falling back to empty."""
    path = (config_dir or _DEFAULT_CONFIG_DIR) / "trusted_apps.yaml"
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        trusted_raw = data.get("trusted", {})
        trusted = {
            platform: [TrustedDeveloper(**entry) for entry in devs]
            for platform, devs in trusted_raw.items()
        }
        return TrustedAppsConfig(trusted=trusted)
    return TrustedAppsConfig()
