# CLAUDE.md — Groundskeeper

## Project Summary

Groundskeeper is a cross-platform permission auditor CLI tool written in Python. It queries platform APIs (GitHub, Google, Slack, etc.), normalizes permission grants into a unified schema, detects risk patterns, and outputs results as terminal tables, JSON, or markdown reports.

## Tech Stack

- **Language:** Python 3.11+
- **CLI framework:** click
- **Data models:** pydantic
- **HTTP client:** httpx
- **Terminal output:** rich
- **Config parsing:** pyyaml
- **Credential storage:** keyring
- **Testing:** pytest, pytest-cov

## Project Structure

```
groundskeeper/
├── core/
│   ├── scanner.py       # Scanning orchestrator — coordinates platform adapters
│   ├── models.py        # Pydantic models: PermissionGrant, Scope, ResourceAccess, etc.
│   └── flags.py         # Risk-pattern detection engine with pluggable rules
├── platforms/
│   ├── base.py          # PlatformAdapter ABC — all adapters implement this
│   ├── github.py        # GitHub REST API integration
│   ├── google.py        # Google OAuth2 + Admin SDK integration
│   └── slack.py         # Slack Web API integration
├── output/
│   ├── table.py         # Rich terminal table formatter
│   ├── json.py          # JSON export
│   └── report.py        # Markdown audit report generator
├── config/
│   ├── trusted_apps.yaml
│   └── thresholds.yaml
└── groundskeeper.py     # CLI entry point (click app)
```

## Key Commands

```bash
# Run tests
pytest tests/

# Run tests with coverage
pytest tests/ --cov=groundskeeper --cov-report=term-missing

# Run the CLI
python -m groundskeeper scan
python -m groundskeeper scan --platform github
python -m groundskeeper scan --flagged
python -m groundskeeper report --output audit.md
```

## Architecture Conventions

- **Platform adapters** inherit from `PlatformAdapter` in `platforms/base.py`. Each adapter implements `authenticate()`, `scan()`, and `revoke()`. The `scan()` method must return `list[PermissionGrant]`.
- **Data models** live in `core/models.py` using pydantic. `PermissionGrant` is the central type — all platform data gets normalized into it.
- **Flagging rules** are functions in `core/flags.py` with signature `(grant, all_grants, config) -> Flag | None`. Rules are registered in a list and executed sequentially.
- **Output formatters** in `output/` each take a `list[PermissionGrant]` and render it.

## Coding Style

- Use type hints on all function signatures.
- Use `httpx` (not `requests`) for HTTP calls. Prefer async where it simplifies concurrent platform scanning.
- Platform adapters should handle API errors gracefully and return partial results rather than crashing the entire scan.
- Configuration is loaded from YAML files in `config/`. Thresholds and trusted app lists are separate files.
- No telemetry or external network calls beyond the platform APIs being audited.

## Testing

- Unit tests use recorded API response fixtures (not live API calls).
- Integration tests are gated behind `--run-integration` and require real credentials.
- Each platform adapter should have its own test file: `tests/test_github.py`, `tests/test_google.py`, etc.
- The flagging engine is tested with synthetic `PermissionGrant` objects.
- Output formatters use snapshot tests.

## Important Patterns

- Credentials come from environment variables (`GROUNDSKEEPER_GITHUB_TOKEN`, etc.) or `~/.groundskeeper/credentials.yaml` (keyring-encrypted).
- The scanner in `core/scanner.py` iterates over registered platform adapters, calls `scan()` on each, merges results, then passes the full list through the flagging engine.
- The `split_grant` flag rule needs access to all grants (not just the current one) to detect apps that hold permissions across multiple grant types on the same platform.

## Common Pitfalls

- GitHub splits app access across three different settings pages / API endpoints (installed apps, authorized apps, OAuth apps). The GitHub adapter must query all three.
- Google Admin SDK requires Workspace admin credentials for org-level scans. Individual user scanning is more limited.
- Token refresh activity on GitHub is inferred from audit log events, not from a direct API field.
