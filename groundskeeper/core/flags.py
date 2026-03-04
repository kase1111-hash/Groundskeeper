"""Risk pattern detection engine — stub for Phase 3 implementation."""

from __future__ import annotations

from groundskeeper.core.models import PermissionGrant, ThresholdConfig, TrustedAppsConfig


class FlagEngine:
    """Applies risk-detection rules to permission grants."""

    def evaluate(
        self,
        grants: list[PermissionGrant],
        config: ThresholdConfig,
        trusted: TrustedAppsConfig,
    ) -> list[PermissionGrant]:
        """Run all registered rules against grants. Returns grants with flags attached.

        Full implementation in Phase 3.
        """
        return grants
