"""Terminal table output — stub for Phase 4 implementation."""

from __future__ import annotations

from groundskeeper.core.models import PermissionGrant


def render_table(grants: list[PermissionGrant]) -> None:
    """Render permission grants as a rich terminal table. Full implementation in Phase 4."""
    print(f"{len(grants)} grants found")
