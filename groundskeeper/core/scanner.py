"""Platform-agnostic scanning orchestrator."""

from __future__ import annotations

from groundskeeper.core.models import PermissionGrant
from groundskeeper.platforms.base import PlatformAdapter


class Scanner:
    """Orchestrates platform adapters to collect and process permission grants."""

    def __init__(self) -> None:
        self._adapters: dict[str, PlatformAdapter] = {}

    def register(self, adapter: PlatformAdapter) -> None:
        """Register a platform adapter."""
        self._adapters[adapter.platform_name()] = adapter

    def scan(self, platform: str | None = None) -> list[PermissionGrant]:
        """Run adapters and collect permission grants.

        Args:
            platform: If provided, only scan this platform. Otherwise scan all.

        Returns:
            Combined list of permission grants from all scanned platforms.
        """
        adapters = self._adapters
        if platform:
            if platform not in adapters:
                raise ValueError(
                    f"Unknown platform '{platform}'. "
                    f"Available: {', '.join(sorted(adapters.keys()))}"
                )
            adapters = {platform: adapters[platform]}

        grants: list[PermissionGrant] = []
        for adapter in adapters.values():
            grants.extend(adapter.scan())

        return grants

    @property
    def platforms(self) -> list[str]:
        """Return list of registered platform names."""
        return sorted(self._adapters.keys())
