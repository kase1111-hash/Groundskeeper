"""Unified permission grant schema and supporting data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AccessLevel(str, Enum):
    """Permission access level for a scope."""

    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"
    EXECUTE = "execute"
    ADMIN = "admin"


class GrantType(str, Enum):
    """Type of permission grant on a platform."""

    OAUTH_APP = "oauth_app"
    INSTALLED_APP = "installed_app"
    AUTHORIZED_APP = "authorized_app"
    PAT = "pat"
    DEPLOY_KEY = "deploy_key"
    API_KEY = "api_key"
    BOT_TOKEN = "bot_token"
    SERVICE_ACCOUNT = "service_account"


class Status(str, Enum):
    """Current status of a permission grant."""

    ACTIVE = "active"
    DORMANT = "dormant"
    FLAGGED = "flagged"
    REVOKED = "revoked"


class FlagType(str, Enum):
    """Risk flag categories."""

    OVERPROVISION = "overprovision"
    DORMANT_AUTHORITY = "dormant_authority"
    SCOPE_CREEP = "scope_creep"
    PHANTOM_CYCLING = "phantom_cycling"
    BLANKET_ACCESS = "blanket_access"
    UNKNOWN_DEVELOPER = "unknown_developer"
    SPLIT_GRANT = "split_grant"


class Scope(BaseModel):
    """A single permission scope with its access level."""

    resource: str
    access: AccessLevel


class ResourceAccess(BaseModel):
    """Describes what resources a grant can touch."""

    type: str = Field(description="'all', 'specific', or 'none'")
    resources: list[str] = Field(default_factory=list)
    count: int = 0


class TokenActivity(BaseModel):
    """Credential refresh frequency and pattern data."""

    last_refresh: datetime | None = None
    refresh_count_24h: int = 0
    refresh_count_7d: int = 0
    has_user_activity: bool = True


class Flag(BaseModel):
    """A risk flag attached to a permission grant."""

    type: FlagType
    description: str


class PermissionGrant(BaseModel):
    """Core data structure representing a single permission grant on any platform."""

    id: str
    app_name: str
    app_developer: str
    platform: str
    grant_type: GrantType
    scopes: list[Scope]
    resource_access: ResourceAccess
    installed_at: datetime
    last_active: datetime | None = None
    token_activity: TokenActivity | None = None
    flags: list[Flag] = Field(default_factory=list)
    status: Status = Status.ACTIVE
    metadata: dict = Field(default_factory=dict)


class ThresholdConfig(BaseModel):
    """Configurable thresholds for the flagging engine."""

    dormancy_days: int = 90
    phantom_cycle_hours: int = 24
    max_blanket_repos: int = 5
    overprovision_lookback_days: int = 30


class TrustedDeveloper(BaseModel):
    """A trusted developer entry."""

    developer: str
    expected_scopes: list[str] = Field(default_factory=list)


class TrustedAppsConfig(BaseModel):
    """Trusted applications whitelist, keyed by platform."""

    trusted: dict[str, list[TrustedDeveloper]] = Field(default_factory=dict)

    def is_trusted(self, platform: str, developer: str) -> bool:
        """Check if a developer is trusted on a given platform."""
        platform_trusted = self.trusted.get(platform, [])
        return any(t.developer == developer for t in platform_trusted)


class AuditEvent(BaseModel):
    """A single audit log entry from a platform."""

    timestamp: datetime
    action: str
    actor: str
    target: str | None = None
    details: dict = Field(default_factory=dict)
