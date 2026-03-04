"""JSON export output — stub for Phase 4 implementation."""

from __future__ import annotations

import json as json_lib

from groundskeeper.core.models import PermissionGrant


def render_json(grants: list[PermissionGrant]) -> str:
    """Serialize grants to formatted JSON. Full implementation in Phase 4."""
    data = [grant.model_dump(mode="json") for grant in grants]
    return json_lib.dumps(data, indent=2)
