"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from groundskeeper.core.models import (
    AccessLevel,
    GrantType,
    PermissionGrant,
    ResourceAccess,
    Scope,
    Status,
    TokenActivity,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        help="Run integration tests against live platform APIs (needs real credentials).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: calls a live platform API")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(reason="needs --run-integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def sample_grant() -> PermissionGrant:
    """A typical GitHub installed app grant for use in tests."""
    return PermissionGrant(
        id="gh-install-12345",
        app_name="CI Bot",
        app_developer="ci-corp",
        platform="github",
        grant_type=GrantType.INSTALLED_APP,
        scopes=[
            Scope(resource="code", access=AccessLevel.READ),
            Scope(resource="actions", access=AccessLevel.READ_WRITE),
        ],
        resource_access=ResourceAccess(
            type="specific",
            resources=["repo-a", "repo-b"],
            count=2,
        ),
        installed_at=datetime(2025, 6, 15, tzinfo=UTC),
        last_active=datetime(2026, 3, 1, tzinfo=UTC),
        status=Status.ACTIVE,
    )


@pytest.fixture
def dormant_grant() -> PermissionGrant:
    """A grant that hasn't been used in a long time."""
    return PermissionGrant(
        id="gh-oauth-99999",
        app_name="Forgotten Tool",
        app_developer="unknown-dev",
        platform="github",
        grant_type=GrantType.OAUTH_APP,
        scopes=[
            Scope(resource="code", access=AccessLevel.READ_WRITE),
        ],
        resource_access=ResourceAccess(type="all", resources=[], count=42),
        installed_at=datetime(2024, 1, 10, tzinfo=UTC),
        last_active=datetime(2024, 3, 5, tzinfo=UTC),
        status=Status.ACTIVE,
    )


@pytest.fixture
def grant_with_token_activity() -> PermissionGrant:
    """A grant with phantom token cycling activity."""
    return PermissionGrant(
        id="gh-install-77777",
        app_name="Phantom App",
        app_developer="shady-inc",
        platform="github",
        grant_type=GrantType.INSTALLED_APP,
        scopes=[
            Scope(resource="code", access=AccessLevel.READ_WRITE),
        ],
        resource_access=ResourceAccess(type="all", resources=[], count=10),
        installed_at=datetime(2025, 9, 1, tzinfo=UTC),
        last_active=datetime(2026, 3, 1, tzinfo=UTC),
        token_activity=TokenActivity(
            last_refresh=datetime(2026, 3, 4, tzinfo=UTC),
            refresh_count_24h=6,
            refresh_count_7d=42,
            has_user_activity=False,
        ),
        status=Status.ACTIVE,
    )
