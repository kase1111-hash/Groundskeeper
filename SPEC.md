# Groundskeeper — Technical Specification

## Overview

Groundskeeper is a cross-platform permission auditor that queries platform APIs, normalizes permission grants into a unified schema, applies risk-pattern detection, and presents results via CLI output or exportable reports. It is a Python CLI tool designed for individual developers and small teams who want visibility into what third-party applications have access to their accounts.

## Goals

1. **Unified visibility** — Flatten permission grants from multiple platforms into a single queryable view.
2. **Risk detection** — Automatically flag grants that match known risk patterns (dormancy, overprovision, phantom cycling, etc.).
3. **Actionable output** — Provide terminal tables, JSON exports, and markdown reports that can feed into security reviews or automation.
4. **Credential sovereignty** — Store all credentials locally, never transmit telemetry, and operate fully offline after API calls complete.

## Non-Goals

- Groundskeeper is not a SIEM or log aggregation platform.
- It does not provide continuous real-time monitoring (the `watch` command polls on an interval).
- It does not manage or provision permissions — it audits them. The `revoke` command is a convenience wrapper, not a policy engine.

---

## Data Model

### PermissionGrant

The core data structure. Every platform adapter must produce instances of this schema.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | Yes | Unique identifier (platform-scoped) |
| `app_name` | `str` | Yes | Display name of the authorized application |
| `app_developer` | `str` | Yes | Developer or organization that published the app |
| `platform` | `str` | Yes | Platform identifier (`github`, `google`, `slack`, etc.) |
| `grant_type` | `GrantType` | Yes | Enum: `oauth_app`, `installed_app`, `authorized_app`, `pat`, `deploy_key`, `api_key`, `bot_token`, `service_account` |
| `scopes` | `list[Scope]` | Yes | List of permission scopes with read/write/execute designators |
| `resource_access` | `ResourceAccess` | Yes | What resources the grant touches (repos, drives, channels, etc.) |
| `installed_at` | `datetime` | Yes | When the grant was created |
| `last_active` | `datetime \| None` | No | Last time the app used its credentials |
| `token_activity` | `TokenActivity \| None` | No | Credential refresh frequency and pattern data |
| `flags` | `list[Flag]` | No | Risk flags detected by the flagging engine |
| `status` | `Status` | Yes | Enum: `active`, `dormant`, `flagged`, `revoked` |
| `metadata` | `dict` | No | Platform-specific extra data |

### Scope

| Field | Type | Description |
|-------|------|-------------|
| `resource` | `str` | What the scope covers (`code`, `issues`, `drive`, `gmail`, `channels`, etc.) |
| `access` | `AccessLevel` | Enum: `read`, `write`, `read_write`, `execute`, `admin` |

### ResourceAccess

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | `all`, `specific`, or `none` |
| `resources` | `list[str]` | List of specific resource names/IDs (empty if `type` is `all`) |
| `count` | `int` | Total number of accessible resources |

### TokenActivity

| Field | Type | Description |
|-------|------|-------------|
| `last_refresh` | `datetime \| None` | When the token was last refreshed |
| `refresh_count_24h` | `int` | Number of refreshes in the last 24 hours |
| `refresh_count_7d` | `int` | Number of refreshes in the last 7 days |
| `has_user_activity` | `bool` | Whether refreshes correlate with user-initiated actions |

---

## Architecture

### Component Diagram

```
┌──────────────────────────────────────────────────────┐
│                   CLI (groundskeeper.py)              │
│  click-based command parser                          │
│  Commands: scan, report, revoke, watch, config       │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│                  Scanner (core/scanner.py)            │
│  Orchestrates platform adapters                      │
│  Collects PermissionGrant instances                  │
│  Passes results to flagging engine                   │
└──────────┬───────────────────┬───────────────────────┘
           │                   │
┌──────────▼──────────┐  ┌─────▼──────────────────────┐
│  Platform Adapters  │  │  Flagging Engine            │
│  platforms/base.py  │  │  core/flags.py              │
│  platforms/github.py│  │                             │
│  platforms/google.py│  │  Applies risk rules to      │
│  platforms/slack.py │  │  PermissionGrant list        │
└─────────────────────┘  └─────────────┬──────────────┘
                                       │
                         ┌─────────────▼──────────────┐
                         │  Output Formatters          │
                         │  output/table.py            │
                         │  output/json.py             │
                         │  output/report.py           │
                         └────────────────────────────┘
```

### Platform Adapter Interface

Every platform adapter must implement `PlatformAdapter` (defined in `platforms/base.py`):

```python
class PlatformAdapter(ABC):
    """Base class for all platform integrations."""

    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g., 'github')."""

    @abstractmethod
    def authenticate(self, credentials: dict) -> None:
        """Validate and store credentials for API access."""

    @abstractmethod
    def scan(self) -> list[PermissionGrant]:
        """Query the platform API and return normalized grants."""

    @abstractmethod
    def revoke(self, grant_id: str) -> bool:
        """Revoke a specific grant. Return True on success."""

    def get_audit_log(self, since: datetime) -> list[AuditEvent]:
        """Optional: Fetch audit log entries since a given time."""
        return []
```

### Flagging Engine

The flagging engine (`core/flags.py`) receives a list of `PermissionGrant` objects and applies rule functions. Each rule is a callable with the signature:

```python
def rule(grant: PermissionGrant, all_grants: list[PermissionGrant], config: ThresholdConfig) -> Flag | None
```

Built-in rules:

| Rule | Trigger Condition |
|------|-------------------|
| `overprovision` | App has `write` or `read_write` scope but `last_active` shows no write operations in audit log |
| `dormant_authority` | `last_active` is `None` or older than `dormancy_days` threshold, and status is `active` |
| `scope_creep` | Granted scopes exceed the app's declared/documented purpose (requires trusted_apps.yaml metadata) |
| `phantom_cycling` | `token_activity.refresh_count_24h > 0` and `token_activity.has_user_activity is False` |
| `blanket_access` | `resource_access.type == "all"` and `resource_access.count > max_blanket_repos` |
| `unknown_developer` | `app_developer` not found in `trusted_apps.yaml` for the given platform |
| `split_grant` | Multiple `PermissionGrant` entries exist for the same `app_name` on the same `platform` with different `grant_type` values |

Rules are registered in a list and executed sequentially. Custom rules can be added by appending callables to the rule registry.

---

## CLI Commands

Built on [click](https://click.palletsprojects.com/).

### `groundskeeper scan`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--platform` | `str` | all | Scan a specific platform only |
| `--flagged` | `bool` | `False` | Show only grants with flags |
| `--format` | `str` | `table` | Output format: `table`, `json` |
| `--quiet` | `bool` | `False` | Suppress progress output |

### `groundskeeper report`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output` | `path` | stdout | Write markdown report to file |
| `--platform` | `str` | all | Scope report to a specific platform |
| `--include-clean` | `bool` | `False` | Include unflagged grants in report |

### `groundskeeper revoke`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--platform` | `str` | required | Target platform |
| `--app` | `str` | required | App name to revoke |
| `--grant-type` | `str` | all | Revoke a specific grant type only |
| `--yes` | `bool` | `False` | Skip confirmation prompt |

### `groundskeeper watch`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--interval` | `str` | `24h` | Polling interval (e.g., `1h`, `6h`, `24h`) |
| `--platform` | `str` | all | Watch a specific platform only |
| `--notify` | `str` | `stdout` | Notification method: `stdout`, `webhook`, `email` |

### `groundskeeper config`

Subcommands: `config set`, `config get`, `config init`. Manages `~/.groundskeeper/` directory, credentials, and threshold/trusted-app files.

---

## Platform-Specific Implementation Notes

### GitHub (`platforms/github.py`)

**APIs used:**
- `GET /user/installations` — Installed GitHub Apps
- `GET /user/installations/{id}/repositories` — Repos accessible to each app
- `GET /applications/grants` — Authorized OAuth Apps
- `GET /user/keys` — SSH keys
- `GET /user/gpg_keys` — GPG keys
- REST audit log endpoints (org-level, requires `read:audit_log`)
- `GET /user/tokens` — PATs (via Settings API, may require scraping or GraphQL)

**Grant types mapped:**
- Installed GitHub App → `installed_app`
- Authorized GitHub App → `authorized_app`
- Authorized OAuth App → `oauth_app`
- Personal Access Token → `pat`
- Deploy Key → `deploy_key`

**Notes:**
- GitHub splits app access across three separate settings pages. The adapter must query all three endpoints and cross-reference results by app name/developer.
- Token refresh activity for GitHub Apps can be inferred from audit log `integration_installation.*` events.

### Google (`platforms/google.py`)

**APIs used:**
- Google OAuth2 token info endpoint
- Admin SDK `tokens.list` — Third-party app tokens for a user
- Admin SDK `activities.list` — Audit log for token usage
- Google Cloud `projects.getIamPolicy` — API credential access

**Grant types mapped:**
- Third-party app with OAuth consent → `oauth_app`
- API key → `api_key`
- Service account → `service_account`

**Notes:**
- Admin SDK requires Google Workspace admin credentials for full org-level scanning.
- Individual user scanning is limited to the user's own OAuth grants via the `tokeninfo` and connected apps page.

### Slack (`platforms/slack.py`)

**APIs used:**
- `admin.apps.approved.list` — Approved workspace apps
- `admin.apps.restricted.list` — Restricted apps
- `apps.connections.open` — Bot token validation
- Audit Logs API — App activity events

**Grant types mapped:**
- Workspace app installation → `installed_app`
- Bot token → `bot_token`
- Workflow integration → `authorized_app`

---

## Credential Storage

Credentials are stored in `~/.groundskeeper/credentials.yaml`. The file is encrypted at rest using the system keyring (via the `keyring` Python package).

Fallback: if no system keyring is available, credentials can be provided via environment variables:

| Variable | Platform |
|----------|----------|
| `GROUNDSKEEPER_GITHUB_TOKEN` | GitHub PAT |
| `GROUNDSKEEPER_GOOGLE_CREDENTIALS` | Path to Google OAuth2 client credentials JSON |
| `GROUNDSKEEPER_SLACK_TOKEN` | Slack user token |

---

## Configuration Files

### `config/thresholds.yaml`

```yaml
dormancy_days: 90
phantom_cycle_hours: 24
max_blanket_repos: 5
overprovision_lookback_days: 30
```

### `config/trusted_apps.yaml`

```yaml
trusted:
  github:
    - developer: "anthropics"
    - developer: "github"
    - developer: "actions"
  google:
    - developer: "google.com"
    - developer: "googleapis.com"
  slack:
    - developer: "slack"
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `click` | CLI framework |
| `rich` | Terminal table rendering and progress indicators |
| `httpx` | HTTP client for API calls |
| `pydantic` | Data model validation and serialization |
| `keyring` | System keyring integration for credential encryption |
| `pyyaml` | YAML configuration parsing |
| `python-dateutil` | Date/time parsing and relative time display |

Target Python version: **3.11+**

---

## Testing Strategy

- **Unit tests** — Each platform adapter is tested against recorded API responses (fixtures). The flagging engine is tested with synthetic `PermissionGrant` objects.
- **Integration tests** — Optional, gated behind `--run-integration` pytest flag. Require live API credentials in environment.
- **Output tests** — Snapshot tests for table, JSON, and markdown output formats.
- **Test runner** — `pytest` with `pytest-cov` for coverage.

```bash
# Run all unit tests
pytest tests/

# Run with coverage
pytest tests/ --cov=groundskeeper --cov-report=term-missing

# Run integration tests (requires credentials)
pytest tests/ --run-integration
```

---

## Phased Delivery

### Phase 1 — Core (MVP)
- Data model (`core/models.py`)
- GitHub adapter (`platforms/github.py`)
- Google adapter (`platforms/google.py`)
- Flagging engine with all 7 built-in rules
- CLI: `scan`, `report` commands
- Table and JSON output
- Credential storage with keyring
- Unit test suite

### Phase 2 — Extended Platforms
- Slack adapter
- Microsoft/Azure adapter
- GitLab adapter
- CLI: `revoke` command
- Markdown report generator
- Webhook notifications for `watch`

### Phase 3 — Infrastructure
- AWS IAM adapter
- Docker Hub adapter
- npm adapter
- CLI: `watch` command with background daemon mode
- Email notifications
- Custom rule loading from user config

---

## Security Considerations

- Groundskeeper itself requires broad read access to audit APIs. Users should create dedicated, minimal-scope credentials for it.
- The tool never writes data to any platform API except during explicit `revoke` operations (which require interactive confirmation by default).
- No telemetry, no network calls beyond the configured platform APIs.
- Credential file permissions should be `0600`. The tool should warn if permissions are too open.
- API responses are processed in memory and not persisted to disk unless the user explicitly requests report output.
