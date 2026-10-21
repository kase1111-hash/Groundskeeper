"""Tests for the GitHub adapter, served from recorded-style API fixtures."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from groundskeeper.core.credentials import load_credentials
from groundskeeper.core.models import (
    AccessLevel,
    GrantType,
    PermissionGrant,
    ResourceAccess,
    Scope,
    Status,
)
from groundskeeper.platforms.github import API_URL, UNKNOWN_DEVELOPER, GitHubAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "github"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeGitHub:
    """Serves fixture responses for the GitHub endpoints the adapter calls."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, int], Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: list[httpx.Request] = []

    def add(
        self,
        path: str,
        fixture: str | None = None,
        *,
        page: int = 1,
        next_page: int | None = None,
        status: int = 200,
        body: dict | None = None,
    ) -> None:
        """Answer GET ``path`` (at ``page``) with a fixture file or a JSON body."""
        if fixture:
            body = load_fixture(fixture)
        headers = {}
        if next_page:
            headers["Link"] = f'<{API_URL}{path}?per_page=100&page={next_page}>; rel="next"'
        self.routes[(path, page)] = lambda request: httpx.Response(
            status, json=body, headers=headers
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get((request.url.path, int(request.url.params.get("page", 1))))
        if route is None:
            return httpx.Response(404, json={"message": "Not Found"})
        return route(request)

    def requested(self, path: str) -> list[httpx.Request]:
        """The requests made for ``path``, in order."""
        return [request for request in self.requests if request.url.path == path]

    def adapter(self) -> GitHubAdapter:
        """An adapter that talks to this fake, already authenticated."""
        adapter = GitHubAdapter(transport=httpx.MockTransport(self.handle))
        adapter.authenticate({"token": "test-token"})
        return adapter


@pytest.fixture
def github() -> FakeGitHub:
    """Four installations over two pages. old-ci-bot is private, so /apps answers 404."""
    fake = FakeGitHub()
    fake.add("/user", "user.json")
    fake.add("/user/installations", "installations_page1.json", next_page=2)
    fake.add("/user/installations", "installations_page2.json", page=2)
    fake.add("/user/installations/1001/repositories", "installation_1001_repositories.json")
    fake.add(
        "/user/installations/1002/repositories",
        "installation_1002_repositories_page1.json",
        next_page=2,
    )
    fake.add(
        "/user/installations/1002/repositories",
        "installation_1002_repositories_page2.json",
        page=2,
    )
    fake.add("/user/installations/1003/repositories", "installation_1003_repositories.json")
    fake.add("/user/installations/1004/repositories", "installation_1004_repositories.json")
    fake.add("/apps/build-bot", "app_build-bot.json")
    fake.add("/apps/review-helper", "app_review-helper.json")
    return fake


def scan_by_id(github: FakeGitHub) -> dict[str, PermissionGrant]:
    return {grant.id: grant for grant in github.adapter().scan()}


class TestAuthenticate:
    def test_missing_token_raises_clear_error(self):
        with pytest.raises(ValueError, match="GROUNDSKEEPER_GITHUB_TOKEN"):
            GitHubAdapter().authenticate({})

    def test_rejected_token_raises_clear_error(self, github: FakeGitHub):
        github.add("/user", status=401, body={"message": "Bad credentials"})
        adapter = GitHubAdapter(transport=httpx.MockTransport(github.handle))
        with pytest.raises(ValueError, match="expired or revoked"):
            adapter.authenticate({"token": "expired-token"})

    def test_other_errors_propagate(self, github: FakeGitHub):
        github.add("/user", status=503, body={"message": "Service Unavailable"})
        adapter = GitHubAdapter(transport=httpx.MockTransport(github.handle))
        with pytest.raises(httpx.HTTPStatusError):
            adapter.authenticate({"token": "test-token"})

    def test_sends_token_and_api_headers(self, github: FakeGitHub):
        adapter = github.adapter()
        assert adapter.login == "octocat"
        headers = github.requested("/user")[0].headers
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    def test_scan_requires_authentication(self):
        with pytest.raises(RuntimeError, match="authenticate"):
            GitHubAdapter().scan()


class TestScan:
    def test_platform_name(self):
        assert GitHubAdapter().platform_name() == "github"

    def test_follows_pagination_across_installation_pages(self, github: FakeGitHub):
        grants = github.adapter().scan()
        assert [grant.id for grant in grants] == [
            "gh-install-1001",
            "gh-install-1002",
            "gh-install-1003",
            "gh-install-1004",
        ]
        first, second = github.requested("/user/installations")
        assert first.url.params["per_page"] == "100"
        assert second.url.params["page"] == "2"

    def test_normalizes_installed_app(self, github: FakeGitHub):
        grant = scan_by_id(github)["gh-install-1001"]
        assert grant.app_name == "Build Bot"
        assert grant.app_developer == "buildco"
        assert grant.platform == "github"
        assert grant.grant_type == GrantType.INSTALLED_APP
        assert grant.installed_at == datetime(2025, 9, 1, 14, 2, 11, tzinfo=UTC)
        assert grant.last_active == datetime(2026, 2, 10, 8, 30, tzinfo=UTC)
        assert grant.status == Status.ACTIVE
        assert grant.token_activity is None
        assert grant.flags == []
        assert grant.metadata == {
            "installation_id": 1001,
            "app_slug": "build-bot",
            "account": "octocat",
            "html_url": "https://github.com/settings/installations/1001",
            "suspended_at": None,
        }

    def test_maps_permissions_to_scopes(self, github: FakeGitHub):
        grants = scan_by_id(github)
        assert grants["gh-install-1002"].scopes == [
            Scope(resource="contents", access=AccessLevel.READ),
            Scope(resource="issues", access=AccessLevel.READ_WRITE),
            Scope(resource="metadata", access=AccessLevel.READ),
            Scope(resource="pull_requests", access=AccessLevel.READ_WRITE),
        ]
        assert Scope(resource="repository_projects", access=AccessLevel.ADMIN) in (
            grants["gh-install-1003"].scopes
        )

    def test_unrecognized_permission_level_counts_as_admin(self, github: FakeGitHub):
        page = load_fixture("installations_page1.json")
        page["installations"][0]["permissions"] = {"contents": "maintain"}
        github.add("/user/installations", body=page)
        grant = scan_by_id(github)["gh-install-1001"]
        assert grant.scopes == [Scope(resource="contents", access=AccessLevel.ADMIN)]

    def test_all_repositories_reports_count_only(self, github: FakeGitHub):
        grant = scan_by_id(github)["gh-install-1001"]
        assert grant.resource_access == ResourceAccess(type="all", resources=[], count=42)
        request = github.requested("/user/installations/1001/repositories")[0]
        assert request.url.params["per_page"] == "1"

    def test_selected_repositories_follow_pagination(self, github: FakeGitHub):
        grant = scan_by_id(github)["gh-install-1002"]
        assert grant.resource_access == ResourceAccess(
            type="specific",
            resources=["octocat/Hello-World", "octocat/Spoon-Knife", "octocat/linguist"],
            count=3,
        )

    def test_suspended_installation_is_dormant(self, github: FakeGitHub):
        grant = scan_by_id(github)["gh-install-1003"]
        assert grant.status == Status.DORMANT
        assert grant.metadata["suspended_at"] == "2024-01-08T09:15:00Z"

    def test_private_app_falls_back_to_slug(
        self, github: FakeGitHub, caplog: pytest.LogCaptureFixture
    ):
        with caplog.at_level(logging.WARNING):
            grant = scan_by_id(github)["gh-install-1003"]
        assert grant.app_name == "old-ci-bot"
        assert grant.app_developer == UNKNOWN_DEVELOPER
        assert "Could not look up GitHub App 'old-ci-bot': 404 Not Found" in caplog.text

    def test_looks_up_each_app_once(self, github: FakeGitHub):
        grants = scan_by_id(github)
        # build-bot is installed on both octocat and octo-org.
        assert grants["gh-install-1004"].app_name == "Build Bot"
        assert len(github.requested("/apps/build-bot")) == 1


class TestPartialResults:
    def test_refused_installation_listing_warns_and_returns_nothing(
        self, github: FakeGitHub, caplog: pytest.LogCaptureFixture
    ):
        github.add(
            "/user/installations",
            status=403,
            body={"message": "Resource not accessible by personal access token"},
        )
        with caplog.at_level(logging.WARNING):
            assert github.adapter().scan() == []
        assert (
            "Could not list GitHub App installations: "
            "403 Forbidden: Resource not accessible by personal access token"
        ) in caplog.text

    def test_failed_page_keeps_earlier_pages(
        self, github: FakeGitHub, caplog: pytest.LogCaptureFixture
    ):
        github.add("/user/installations", page=2, status=502, body={"message": "Server Error"})
        with caplog.at_level(logging.WARNING):
            grants = github.adapter().scan()
        assert [grant.id for grant in grants] == ["gh-install-1001", "gh-install-1002"]
        assert "Could not list GitHub App installations: 502 Bad Gateway" in caplog.text

    def test_repository_listing_failure_keeps_the_grant(
        self, github: FakeGitHub, caplog: pytest.LogCaptureFixture
    ):
        github.add("/user/installations/1004/repositories", status=403, body={})
        with caplog.at_level(logging.WARNING):
            grants = scan_by_id(github)
        assert len(grants) == 4
        assert grants["gh-install-1004"].resource_access == ResourceAccess(type="specific")
        assert (
            "Could not list repositories for the 'build-bot' installation on octo-org: "
            "403 Forbidden"
        ) in caplog.text

    def test_error_page_without_json(self, github: FakeGitHub, caplog: pytest.LogCaptureFixture):
        github.routes[("/apps/review-helper", 1)] = lambda request: httpx.Response(
            500, text="<html>Oops</html>"
        )
        with caplog.at_level(logging.WARNING):
            grant = scan_by_id(github)["gh-install-1002"]
        assert grant.app_developer == UNKNOWN_DEVELOPER
        assert (
            "Could not look up GitHub App 'review-helper': 500 Internal Server Error"
        ) in caplog.text

    def test_network_error_is_reported(self, github: FakeGitHub, caplog: pytest.LogCaptureFixture):
        def reset(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection reset by peer", request=request)

        github.routes[("/user/installations/1001/repositories", 1)] = reset
        with caplog.at_level(logging.WARNING):
            grant = scan_by_id(github)["gh-install-1001"]
        assert grant.resource_access == ResourceAccess(type="all", count=0)
        assert "connection reset by peer" in caplog.text


class TestRevoke:
    def test_not_supported(self, github: FakeGitHub):
        with pytest.raises(NotImplementedError, match="html_url"):
            github.adapter().revoke("gh-install-1001")


@pytest.mark.integration
class TestLiveGitHub:
    def test_scans_live_account(self, caplog: pytest.LogCaptureFixture):
        credentials = load_credentials("github")
        if not credentials.get("token"):
            pytest.skip("no GitHub token configured")
        adapter = GitHubAdapter()
        adapter.authenticate(credentials)
        with caplog.at_level(logging.WARNING):
            grants = adapter.scan()
        # Fails if GitHub won't list installations for this kind of token.
        assert "Could not list GitHub App installations" not in caplog.text
        assert all(grant.platform == "github" for grant in grants)
