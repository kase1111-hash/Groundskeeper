"""Credential loading for platform adapters."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

# platform -> (environment variable, credentials key it provides)
_ENV_VARS = {
    "github": ("GROUNDSKEEPER_GITHUB_TOKEN", "token"),
}


def load_credentials(platform: str, path: Path | None = None) -> dict:
    """Load credentials for a platform, preferring its environment variable.

    Falls back to the platform's section of ``~/.groundskeeper/credentials.yaml``::

        github:
          token: ghp_...

    The file is read as plaintext for now; keyring encryption comes in Phase 5.
    Returns an empty dict if nothing is configured.
    """
    if platform in _ENV_VARS:
        var, key = _ENV_VARS[platform]
        if value := os.environ.get(var):
            return {key: value}
    path = path or Path.home() / ".groundskeeper" / "credentials.yaml"
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return dict(data.get(platform) or {})
    return {}
