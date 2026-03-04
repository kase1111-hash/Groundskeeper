"""Tests for core data models — serialization, enums, and validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from groundskeeper.core.models import (
    AccessLevel,
    AuditEvent,
    Flag,
    FlagType,
    GrantType,
    PermissionGrant,
    ResourceAccess,
    Scope,
    Status,
    ThresholdConfig,
    TokenActivity,
    TrustedAppsConfig,
    TrustedDeveloper,
)


class TestEnums:
    def test_access_level_values(self):
        assert AccessLevel.READ == "read"
        assert AccessLevel.WRITE == "write"
        assert AccessLevel.READ_WRITE == "read_write"
        assert AccessLevel.EXECUTE == "execute"
        assert AccessLevel.ADMIN == "admin"

    def test_grant_type_values(self):
        assert GrantType.OAUTH_APP == "oauth_app"
        assert GrantType.INSTALLED_APP == "installed_app"
        assert GrantType.PAT == "pat"
        assert GrantType.DEPLOY_KEY == "deploy_key"
        assert GrantType.API_KEY == "api_key"
        assert GrantType.BOT_TOKEN == "bot_token"
        assert GrantType.SERVICE_ACCOUNT == "service_account"

    def test_status_values(self):
        assert Status.ACTIVE == "active"
        assert Status.DORMANT == "dormant"
        assert Status.FLAGGED == "flagged"
        assert Status.REVOKED == "revoked"

    def test_flag_type_values(self):
        assert FlagType.OVERPROVISION == "overprovision"
        assert FlagType.DORMANT_AUTHORITY == "dormant_authority"
        assert FlagType.PHANTOM_CYCLING == "phantom_cycling"
        assert FlagType.BLANKET_ACCESS == "blanket_access"
        assert FlagType.UNKNOWN_DEVELOPER == "unknown_developer"
        assert FlagType.SPLIT_GRANT == "split_grant"
        assert FlagType.SCOPE_CREEP == "scope_creep"


class TestScope:
    def test_create(self):
        scope = Scope(resource="code", access=AccessLevel.READ_WRITE)
        assert scope.resource == "code"
        assert scope.access == AccessLevel.READ_WRITE

    def test_json_round_trip(self):
        scope = Scope(resource="drive", access=AccessLevel.READ)
        data = scope.model_dump(mode="json")
        restored = Scope(**data)
        assert restored == scope


class TestResourceAccess:
    def test_all_repos(self):
        ra = ResourceAccess(type="all", resources=[], count=50)
        assert ra.type == "all"
        assert ra.resources == []
        assert ra.count == 50

    def test_specific_repos(self):
        ra = ResourceAccess(type="specific", resources=["repo-a", "repo-b"], count=2)
        assert len(ra.resources) == 2

    def test_defaults(self):
        ra = ResourceAccess(type="none")
        assert ra.resources == []
        assert ra.count == 0


class TestTokenActivity:
    def test_defaults(self):
        ta = TokenActivity()
        assert ta.last_refresh is None
        assert ta.refresh_count_24h == 0
        assert ta.refresh_count_7d == 0
        assert ta.has_user_activity is True

    def test_phantom_pattern(self):
        ta = TokenActivity(refresh_count_24h=12, has_user_activity=False)
        assert ta.refresh_count_24h == 12
        assert ta.has_user_activity is False


class TestFlag:
    def test_create(self):
        flag = Flag(type=FlagType.DORMANT_AUTHORITY, description="Unused for 180 days")
        assert flag.type == FlagType.DORMANT_AUTHORITY
        assert "180" in flag.description


class TestPermissionGrant:
    def test_create_minimal(self):
        grant = PermissionGrant(
            id="test-1",
            app_name="Test App",
            app_developer="test-dev",
            platform="github",
            grant_type=GrantType.OAUTH_APP,
            scopes=[Scope(resource="code", access=AccessLevel.READ)],
            resource_access=ResourceAccess(type="none"),
            installed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert grant.status == Status.ACTIVE
        assert grant.flags == []
        assert grant.metadata == {}
        assert grant.last_active is None
        assert grant.token_activity is None

    def test_json_round_trip(self, sample_grant: PermissionGrant):
        json_str = sample_grant.model_dump_json()
        restored = PermissionGrant.model_validate_json(json_str)
        assert restored == sample_grant

    def test_dict_round_trip(self, sample_grant: PermissionGrant):
        data = sample_grant.model_dump(mode="json")
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = PermissionGrant(**parsed)
        assert restored == sample_grant

    def test_with_flags(self, sample_grant: PermissionGrant):
        sample_grant.flags = [
            Flag(type=FlagType.BLANKET_ACCESS, description="All repos"),
            Flag(type=FlagType.UNKNOWN_DEVELOPER, description="Untrusted dev"),
        ]
        assert len(sample_grant.flags) == 2
        data = sample_grant.model_dump(mode="json")
        restored = PermissionGrant(**data)
        assert len(restored.flags) == 2
        assert restored.flags[0].type == FlagType.BLANKET_ACCESS

    def test_with_token_activity(self, grant_with_token_activity: PermissionGrant):
        assert grant_with_token_activity.token_activity is not None
        assert grant_with_token_activity.token_activity.refresh_count_24h == 6
        assert grant_with_token_activity.token_activity.has_user_activity is False
        data = grant_with_token_activity.model_dump(mode="json")
        restored = PermissionGrant(**data)
        assert restored.token_activity is not None
        assert restored.token_activity.refresh_count_24h == 6

    def test_metadata_preserved(self):
        grant = PermissionGrant(
            id="test-meta",
            app_name="Meta App",
            app_developer="dev",
            platform="github",
            grant_type=GrantType.PAT,
            scopes=[],
            resource_access=ResourceAccess(type="none"),
            installed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            metadata={"note": "classic token", "expires": "2026-01-01"},
        )
        data = grant.model_dump(mode="json")
        restored = PermissionGrant(**data)
        assert restored.metadata["note"] == "classic token"


class TestThresholdConfig:
    def test_defaults(self):
        config = ThresholdConfig()
        assert config.dormancy_days == 90
        assert config.phantom_cycle_hours == 24
        assert config.max_blanket_repos == 5
        assert config.overprovision_lookback_days == 30

    def test_custom_values(self):
        config = ThresholdConfig(dormancy_days=30, max_blanket_repos=10)
        assert config.dormancy_days == 30
        assert config.max_blanket_repos == 10


class TestTrustedAppsConfig:
    def test_is_trusted_found(self):
        config = TrustedAppsConfig(
            trusted={
                "github": [
                    TrustedDeveloper(developer="anthropics"),
                    TrustedDeveloper(developer="github"),
                ]
            }
        )
        assert config.is_trusted("github", "anthropics") is True
        assert config.is_trusted("github", "github") is True

    def test_is_trusted_not_found(self):
        config = TrustedAppsConfig(
            trusted={"github": [TrustedDeveloper(developer="github")]}
        )
        assert config.is_trusted("github", "unknown-dev") is False

    def test_is_trusted_unknown_platform(self):
        config = TrustedAppsConfig(trusted={})
        assert config.is_trusted("gitlab", "anyone") is False

    def test_empty_config(self):
        config = TrustedAppsConfig()
        assert config.is_trusted("github", "anyone") is False


class TestAuditEvent:
    def test_create(self):
        event = AuditEvent(
            timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
            action="integration_installation.create",
            actor="user123",
            target="repo-a",
            details={"scope": "read"},
        )
        assert event.action == "integration_installation.create"
        assert event.target == "repo-a"

    def test_optional_fields(self):
        event = AuditEvent(
            timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
            action="token.refresh",
            actor="system",
        )
        assert event.target is None
        assert event.details == {}
