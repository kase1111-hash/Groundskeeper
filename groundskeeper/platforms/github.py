"""GitHub platform adapter: GitHub App installations via the REST API.

GitHub's settings split app access across three pages (installed GitHub Apps,
authorized GitHub Apps, authorized OAuth Apps), but the REST API can only list
installations. The endpoint that listed OAuth grants (GET /applications/grants)
was removed along with the OAuth Authorizations API, and no endpoint lists the
GitHub Apps a user has authorized, so this adapter reports installed apps only.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx

from groundskeeper import __version__
from groundskeeper.core.models import (
    AccessLevel,
    GrantType,
    PermissionGrant,
    ResourceAccess,
    Scope,
    Status,
)
from groundskeeper.platforms.base import PlatformAdapter

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"
UNKNOWN_DEVELOPER = "unknown"

# GitHub App permission levels. GitHub's "write" always includes read.
_ACCESS_LEVELS = {
    "read": AccessLevel.READ,
    "write": AccessLevel.READ_WRITE,
    "admin": AccessLevel.ADMIN,
}


class GitHubAdapter(PlatformAdapter):
    """Scans the GitHub Apps installed where the token's user has access."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport
        self._token: str | None = None
        self.login: str | None = None

    def platform_name(self) -> str:
        return "github"

    def authenticate(self, credentials: dict) -> None:
        """Validate the token with ``GET /user``.

        Raises:
            ValueError: If no token is given or GitHub rejects it.
        """
        token = credentials.get("token")
        if not token:
            raise ValueError(
                "No GitHub token found. Set GROUNDSKEEPER_GITHUB_TOKEN, or add it to "
                "~/.groundskeeper/credentials.yaml as:\n  github:\n    token: <token>"
            )
        with self._client(token) as client:
            response = client.get("/user")
        if response.status_code == 401:
            raise ValueError(
                "GitHub rejected the token (401 Bad credentials). It may be expired or "
                "revoked; create a new one and try again."
            )
        response.raise_for_status()
        self._token = token
        self.login = response.json()["login"]

    def scan(self) -> list[PermissionGrant]:
        """Return one grant per GitHub App installation the user can see.

        API errors are logged as warnings, and whatever was collected is returned.
        """
        if self._token is None:
            raise RuntimeError("Call authenticate() before scan().")
        with self._client(self._token) as client:
            installations: list[dict] = []
            try:
                # A loop, not list(), so pages fetched before an error are kept.
                for installation in self._paginate(client, "/user/installations", "installations"):
                    installations.append(installation)  # noqa: PERF402
            except httpx.HTTPError as exc:
                logger.warning("Could not list GitHub App installations: %s", _describe(exc))

            apps: dict[str, dict | None] = {}
            grants = []
            for installation in installations:
                slug = installation["app_slug"]
                if slug not in apps:
                    apps[slug] = self._get_app(client, slug)
                access = self._resource_access(client, installation)
                grants.append(_installation_grant(installation, apps[slug], access))
        return grants

    def revoke(self, grant_id: str) -> bool:
        """Not supported: only the app itself can delete an installation through the API."""
        raise NotImplementedError(
            "Groundskeeper can't revoke GitHub grants yet. Uninstall the app from the "
            "settings page linked in the grant's metadata (html_url)."
        )

    def _client(self, token: str) -> httpx.Client:
        return httpx.Client(
            base_url=API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"groundskeeper/{__version__}",
            },
            timeout=30.0,
            transport=self._transport,
        )

    def _paginate(self, client: httpx.Client, path: str, key: str) -> Iterator[dict]:
        """Yield the items under ``key`` from every page, following Link headers."""
        url: str | None = path
        params: dict | None = {"per_page": 100}
        while url:
            response = client.get(url, params=params)
            response.raise_for_status()
            yield from response.json()[key]
            url = response.links.get("next", {}).get("url")
            params = None  # the next link carries its own query string

    def _get_app(self, client: httpx.Client, slug: str) -> dict | None:
        """Look up an app's name and owner. None if GitHub won't show it, e.g. a private app."""
        try:
            response = client.get(f"/apps/{slug}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Could not look up GitHub App '%s': %s", slug, _describe(exc))
            return None
        return response.json()

    def _resource_access(self, client: httpx.Client, installation: dict) -> ResourceAccess:
        """Describe which repositories an installation can reach."""
        path = f"/user/installations/{installation['id']}/repositories"
        selected = installation["repository_selection"] == "selected"
        repos: list[str] = []
        total = 0
        try:
            if selected:
                for repo in self._paginate(client, path, "repositories"):
                    repos.append(repo["full_name"])
            else:
                # For "all", only the count is needed, and every page carries it.
                response = client.get(path, params={"per_page": 1})
                response.raise_for_status()
                total = response.json()["total_count"]
        except httpx.HTTPError as exc:
            logger.warning(
                "Could not list repositories for the '%s' installation on %s: %s",
                installation["app_slug"],
                _login(installation.get("account")),
                _describe(exc),
            )
        if selected:
            return ResourceAccess(type="specific", resources=repos, count=len(repos))
        return ResourceAccess(type="all", count=total)


def _installation_grant(
    installation: dict, app: dict | None, access: ResourceAccess
) -> PermissionGrant:
    """Normalize an installation, plus its app's details, into a PermissionGrant."""
    return PermissionGrant(
        id=f"gh-install-{installation['id']}",
        app_name=app["name"] if app else installation["app_slug"],
        app_developer=_login((app or {}).get("owner")) or UNKNOWN_DEVELOPER,
        platform="github",
        grant_type=GrantType.INSTALLED_APP,
        scopes=[
            # Unrecognized levels count as admin so new kinds of access can't slip past an audit.
            Scope(resource=name, access=_ACCESS_LEVELS.get(level, AccessLevel.ADMIN))
            for name, level in sorted(installation["permissions"].items())
        ],
        resource_access=access,
        installed_at=installation["created_at"],
        # GitHub exposes no last-used time for installations. updated_at (the last
        # configuration change) is the closest field until audit-log activity lands.
        last_active=installation["updated_at"],
        status=Status.DORMANT if installation.get("suspended_at") else Status.ACTIVE,
        metadata={
            "installation_id": installation["id"],
            "app_slug": installation["app_slug"],
            "account": _login(installation.get("account")),
            "html_url": installation["html_url"],
            "suspended_at": installation.get("suspended_at"),
        },
    )


def _login(account: dict | None) -> str | None:
    """A user's or organization's login. Enterprise accounts have a slug instead."""
    if not account:
        return None
    return account.get("login") or account.get("slug")


def _describe(exc: httpx.HTTPError) -> str:
    """Summarize an HTTP error, including GitHub's own message when it sent one."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return str(exc) or type(exc).__name__
    response = exc.response
    summary = f"{response.status_code} {response.reason_phrase}"
    try:
        message = response.json().get("message")
    except ValueError:
        message = None
    return f"{summary}: {message}" if message else summary
