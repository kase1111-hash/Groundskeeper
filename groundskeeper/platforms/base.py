"""Platform adapter interface — all platform integrations implement this ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from groundskeeper.core.models import AuditEvent, PermissionGrant


class PlatformAdapter(ABC):
    """Base class for all platform integrations."""

    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g., 'github')."""

    @abstractmethod
    def authenticate(self, credentials: dict) -> None:
        """Validate and store credentials for API access.

        Raises:
            ValueError: If credentials are missing or invalid.
        """

    @abstractmethod
    def scan(self) -> list[PermissionGrant]:
        """Query the platform API and return normalized permission grants."""

    @abstractmethod
    def revoke(self, grant_id: str) -> bool:
        """Revoke a specific grant. Return True on success."""

    def get_audit_log(self, since: datetime) -> list[AuditEvent]:
        """Fetch audit log entries since a given time. Optional."""
        return []
