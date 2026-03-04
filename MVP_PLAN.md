# Groundskeeper MVP — 5-Phase Build Plan

## Phase 1: Foundation — Project Scaffolding & Data Models

**Goal:** Set up the Python project structure, dependencies, and the core data models that everything else builds on.

### Deliverables

1. **Project scaffolding**
   - Initialize `pyproject.toml` with project metadata, Python 3.11+ requirement, and all dependencies (`click`, `rich`, `httpx`, `pydantic`, `keyring`, `pyyaml`, `python-dateutil`)
   - Dev dependencies: `pytest`, `pytest-cov`, `ruff`
   - Create the full directory structure:
     ```
     groundskeeper/
     ├── __init__.py
     ├── groundskeeper.py
     ├── core/
     │   ├── __init__.py
     │   ├── models.py
     │   ├── scanner.py
     │   └── flags.py
     ├── platforms/
     │   ├── __init__.py
     │   └── base.py
     ├── output/
     │   ├── __init__.py
     │   ├── table.py
     │   └── json.py
     └── config/
         ├── thresholds.yaml
         └── trusted_apps.yaml
     tests/
     ├── __init__.py
     ├── conftest.py
     └── test_models.py
     ```

2. **Pydantic data models** (`core/models.py`)
   - `AccessLevel` enum: `read`, `write`, `read_write`, `execute`, `admin`
   - `GrantType` enum: `oauth_app`, `installed_app`, `authorized_app`, `pat`, `deploy_key`, `api_key`, `bot_token`, `service_account`
   - `Status` enum: `active`, `dormant`, `flagged`, `revoked`
   - `FlagType` enum: `overprovision`, `dormant_authority`, `scope_creep`, `phantom_cycling`, `blanket_access`, `unknown_developer`, `split_grant`
   - `Scope` model with `resource: str` and `access: AccessLevel`
   - `ResourceAccess` model with `type: str`, `resources: list[str]`, `count: int`
   - `TokenActivity` model with refresh tracking fields
   - `Flag` model with `type: FlagType` and `description: str`
   - `PermissionGrant` model with all fields from the spec
   - `ThresholdConfig` model loaded from `thresholds.yaml`
   - `TrustedAppsConfig` model loaded from `trusted_apps.yaml`

3. **Platform adapter ABC** (`platforms/base.py`)
   - `PlatformAdapter` abstract base class with `platform_name()`, `authenticate()`, `scan()`, `revoke()`, and optional `get_audit_log()`

4. **Configuration loader**
   - Function to locate and load `thresholds.yaml` and `trusted_apps.yaml` from `config/` directory
   - Sensible defaults if files are missing

5. **Tests**
   - `test_models.py`: Validate all models serialize/deserialize correctly, enum values are correct, optional fields work as expected

### Exit Criteria
- `pip install -e .` succeeds
- `pytest tests/test_models.py` passes
- All data models can round-trip through JSON serialization

---

## Phase 2: GitHub Platform Adapter

**Goal:** Build the first real platform integration — GitHub — querying all three app authorization endpoints and normalizing results into `PermissionGrant` objects.

### Deliverables

1. **GitHub adapter** (`platforms/github.py`)
   - `GitHubAdapter(PlatformAdapter)` implementation
   - `authenticate()`: Accept PAT from credentials dict, validate via `GET /user` call
   - `scan()` queries three endpoints and merges results:
     - `GET /user/installations` → `installed_app` grants, with per-installation repo list via `GET /user/installations/{id}/repositories`
     - `GET /applications/grants` → `oauth_app` grants (authorized OAuth apps)
     - Authorized GitHub Apps (via `GET /user/installations` filtered by authorization status) → `authorized_app` grants
   - Scope parsing: Map GitHub permission strings (`contents: write`, `pull_requests: read`, etc.) to `Scope` objects
   - Resource access: Map `repository_selection: "all"` vs specific repo lists to `ResourceAccess`
   - Pagination handling for all endpoints
   - `last_active` populated from installation `updated_at` or access token `last_used_at` where available

2. **Credential loading**
   - Load `GROUNDSKEEPER_GITHUB_TOKEN` from environment variable
   - Fallback to `~/.groundskeeper/credentials.yaml` if it exists (plaintext for now, keyring in later phase)

3. **Tests** (`tests/test_github.py`)
   - Fixture files: recorded JSON responses for each GitHub API endpoint (`tests/fixtures/github/`)
   - Mock `httpx` calls to return fixtures
   - Test: installed apps are correctly normalized to `PermissionGrant`
   - Test: OAuth apps are correctly normalized
   - Test: "all repositories" vs specific repos maps to correct `ResourceAccess`
   - Test: pagination is followed
   - Test: missing/expired token raises clear error

### Exit Criteria
- `GitHubAdapter.scan()` returns a `list[PermissionGrant]` from fixture data
- All grant types are correctly mapped
- Scope and resource access fields are populated accurately
- Test suite passes with 90%+ coverage on `platforms/github.py`

---

## Phase 3: Flagging Engine

**Goal:** Implement all 7 risk-detection rules and the engine that applies them to a list of grants.

### Deliverables

1. **Flagging engine** (`core/flags.py`)
   - `FlagEngine` class with a rule registry (`list[Callable]`)
   - `evaluate(grants: list[PermissionGrant], config: ThresholdConfig, trusted: TrustedAppsConfig) -> list[PermissionGrant]` method that runs all rules against each grant and attaches `Flag` objects
   - Each rule is a standalone function registered in the engine

2. **Built-in rules**
   - `check_dormant_authority`: Flag if `last_active` is `None` or older than `config.dormancy_days` and status is `active`
   - `check_blanket_access`: Flag if `resource_access.type == "all"` and `resource_access.count > config.max_blanket_repos`
   - `check_unknown_developer`: Flag if `app_developer` is not in `trusted_apps` for the grant's platform
   - `check_split_grant`: Flag if multiple grants exist for the same `app_name` + `platform` with different `grant_type` values (requires full grants list)
   - `check_phantom_cycling`: Flag if `token_activity.refresh_count_24h > 0` and `token_activity.has_user_activity is False`
   - `check_overprovision`: Flag if any scope has `write` or `read_write` access but `last_active` shows no recent activity (within `overprovision_lookback_days`)
   - `check_scope_creep`: Flag if granted scopes exceed the app's expected scopes as defined in `trusted_apps.yaml` (only applies to trusted apps with declared expected scopes)

3. **Tests** (`tests/test_flags.py`)
   - One test per rule with a synthetic `PermissionGrant` that triggers it
   - One test per rule with a grant that should NOT trigger it
   - Test that `split_grant` correctly detects cross-grant-type apps
   - Test that the engine attaches multiple flags to a single grant when applicable
   - Test that threshold config values are respected (e.g., changing `dormancy_days` changes which grants are flagged)

### Exit Criteria
- All 7 rules pass their positive and negative test cases
- A grant can accumulate multiple flags
- Config thresholds are respected
- Test suite passes with 90%+ coverage on `core/flags.py`

---

## Phase 4: CLI & Output Formatters

**Goal:** Wire everything together into a working CLI with `scan` and `report` commands, terminal table output, and JSON export.

### Deliverables

1. **Scanner orchestrator** (`core/scanner.py`)
   - `Scanner` class that holds a registry of `PlatformAdapter` instances
   - `scan(platform: str | None) -> list[PermissionGrant]`: Run adapters (all or filtered), collect grants, pass through flagging engine, return results
   - Progress indication via `rich` status/spinner during API calls

2. **Table output** (`output/table.py`)
   - `render_table(grants: list[PermissionGrant]) -> None`: Print a `rich` table to stdout
   - Columns: App (name + developer), Platform, Scope (formatted), Last Used (relative time), Flags (emoji + code)
   - Flag indicators: warning symbols with flag codes (e.g., `DORMANT`, `BLANKET`, `PHANTOM`)
   - Summary line: `N grants found · M flagged · K clean`

3. **JSON output** (`output/json.py`)
   - `render_json(grants: list[PermissionGrant]) -> str`: Serialize grants list to formatted JSON using pydantic's `.model_dump(mode="json")`
   - Print to stdout or write to file

4. **CLI entry point** (`groundskeeper.py`)
   - `scan` command with `--platform`, `--flagged`, `--format`, `--quiet` options
   - `report` command with `--output`, `--platform`, `--include-clean` options (report outputs markdown table, simpler than full report.py from Phase 2)
   - `config init` subcommand: Create `~/.groundskeeper/` directory and skeleton config files
   - Version flag: `--version`
   - Error handling: Clear messages for missing credentials, API errors, network failures

5. **Tests**
   - `tests/test_scanner.py`: Test orchestrator with mock adapters
   - `tests/test_output.py`: Snapshot tests for table and JSON output
   - `tests/test_cli.py`: Click test runner for `scan` and `report` commands with mock scanner

### Exit Criteria
- `groundskeeper scan` produces a formatted table from GitHub API data (or fixture data in tests)
- `groundskeeper scan --format json` produces valid JSON
- `groundskeeper scan --flagged` filters to only flagged grants
- `groundskeeper report --output audit.md` writes a markdown file
- `groundskeeper config init` creates the config directory
- All CLI tests pass

---

## Phase 5: Google Adapter, Credential Storage & Polish

**Goal:** Add the second platform (Google), implement secure credential storage, and ship a polished MVP.

### Deliverables

1. **Google adapter** (`platforms/google.py`)
   - `GoogleAdapter(PlatformAdapter)` implementation
   - `authenticate()`: Load OAuth2 credentials from JSON file path (via `GROUNDSKEEPER_GOOGLE_CREDENTIALS` env var or credentials.yaml)
   - `scan()` for individual users:
     - List third-party app access via Google's connected apps / token management
     - Normalize to `PermissionGrant` with scopes mapped from Google OAuth scope URLs to human-readable names (e.g., `https://www.googleapis.com/auth/drive.readonly` → `Scope(resource="drive", access=AccessLevel.read)`)
   - `scan()` for Workspace admins (if Admin SDK credentials available):
     - `tokens.list` for user-level third-party app tokens
     - Normalize service accounts and API keys
   - Graceful degradation: If admin credentials aren't available, scan what's accessible and note limitations

2. **Credential storage**
   - `~/.groundskeeper/credentials.yaml` with keyring encryption via `keyring` package
   - `groundskeeper config set-credential --platform github --token <token>` command
   - `groundskeeper config set-credential --platform google --credentials-file <path>` command
   - Fallback chain: environment variable → credentials.yaml → prompt user
   - File permission check: warn if `credentials.yaml` is readable by others

3. **Google tests** (`tests/test_google.py`)
   - Fixture files for Google API responses (`tests/fixtures/google/`)
   - Same coverage pattern as GitHub: normalization, scope mapping, error handling

4. **End-to-end integration test** (manual / gated)
   - Document the manual test procedure in `tests/INTEGRATION.md`
   - Checklist: scan GitHub with real token, scan Google with real credentials, verify flags, verify output formats

5. **Polish**
   - `--help` text for all commands is clear and complete
   - Error messages include actionable remediation (e.g., "No GitHub token found. Set GROUNDSKEEPER_GITHUB_TOKEN or run `groundskeeper config set-credential --platform github`")
   - `pyproject.toml` console script entry point: `groundskeeper = "groundskeeper.groundskeeper:cli"`
   - Confirm `pip install .` and `groundskeeper scan --help` work from a clean install

### Exit Criteria
- `groundskeeper scan` works against both GitHub and Google
- Credentials are stored securely and loaded from the fallback chain
- All unit tests pass across models, GitHub adapter, Google adapter, flags, scanner, output, and CLI
- `pip install .` from a clean virtualenv produces a working `groundskeeper` command
- The tool can scan a real GitHub account and produce accurate, flagged output

---

## Summary

| Phase | Focus | Key Output |
|-------|-------|------------|
| 1 | Foundation | Project structure, data models, adapter ABC, config loading |
| 2 | GitHub | First working platform adapter with full test coverage |
| 3 | Flagging | All 7 risk-detection rules with engine and tests |
| 4 | CLI & Output | Working `scan` and `report` commands with table/JSON output |
| 5 | Google & Polish | Second platform, credential storage, install-and-run MVP |

Each phase builds on the previous one. At the end of Phase 5, you have a pip-installable CLI tool that scans GitHub and Google, flags risky permission grants, and outputs results as terminal tables, JSON, or markdown reports.
