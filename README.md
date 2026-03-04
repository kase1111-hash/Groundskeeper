# Groundskeeper

**Cross-platform permission auditor for sovereign infrastructure.**

You installed something six months ago. It asked for "access to your repositories." You clicked Allow. It's been silently refreshing credentials every ten hours since, with read/write on your entire codebase. You didn't know until you read the audit log — and even then, you had to check two separate settings pages to fully revoke it.

Groundskeeper walks the fence line and checks the locks.

## The Problem

Modern platforms scatter permission grants across multiple pages, tabs, and authorization models. GitHub alone splits app access into "Installed GitHub Apps," "Authorized GitHub Apps," and "Authorized OAuth Apps" — three separate pages, none of which reference each other. Google fragments permissions across Account Settings, Workspace Admin, API Console, and the Security dashboard.

The result: phantom permissions. Apps you forgot you authorized, scopes far broader than you intended, credentials cycling autonomously in the background. The information exists in audit logs and API endpoints, but no human is going to manually cross-reference them.

**Dark pattern authorization is functionally indistinguishable from compromise.** The only difference is intent — and you can't audit intent from a log.

## What Groundskeeper Does

Groundskeeper queries platform APIs and flattens every permission grant into a single, unified view:

| Field | Description |
|-------|-------------|
| **App** | Name and developer of the authorized application |
| **Platform** | Where the grant lives (GitHub, Google, Slack, etc.) |
| **Grant Type** | OAuth app, installed app, authorized app, API key, etc. |
| **Scope** | Exactly what it can read, write, or execute |
| **Resource Access** | Which repos/drives/channels/workspaces it touches |
| **Installed** | When the grant was created |
| **Last Active** | When the app last used its credentials |
| **Token Activity** | Credential refresh frequency and pattern |
| **Status** | Active, dormant, or flagged |

One view. No menu diving.

## Supported Platforms

### Phase 1 — Core
- **GitHub** — Installed apps, authorized apps, OAuth apps, PATs, deploy keys
- **Google** — Third-party app access, OAuth grants, API credentials, Workspace admin connections

### Phase 2 — Extended
- **Slack** — App installations, bot tokens, workflow integrations
- **Microsoft/Azure** — Entra ID app registrations, OAuth grants, API permissions
- **GitLab** — Applications, access tokens, deploy tokens

### Phase 3 — Infrastructure
- **AWS** — IAM roles, cross-account access, third-party integrations
- **Docker Hub** — Access tokens, connected services
- **npm** — Access tokens, automation tokens, granular tokens

## Flagging Rules

Groundskeeper flags grants that match common risk patterns:

- **Overprovision** — App has write scope but has never performed a write operation
- **Dormant authority** — App hasn't been actively used in 90+ days but maintains live credentials
- **Scope creep** — App's granted permissions exceed what its documented purpose requires
- **Phantom cycling** — Automated token regeneration with no corresponding user-initiated activity
- **Blanket access** — "All repositories" / "All drives" / "All channels" grants
- **Unknown developer** — App developer doesn't match a known/trusted list
- **Split grant** — App holds permissions across multiple authorization types on the same platform (the two-page GitHub problem)

## Architecture

```
groundskeeper/
├── core/
│   ├── scanner.py          # Platform-agnostic scanning orchestrator
│   ├── models.py           # Unified permission grant schema
│   └── flags.py            # Risk pattern detection engine
├── platforms/
│   ├── github.py           # GitHub REST API + audit log integration
│   ├── google.py           # Google OAuth2 + Admin SDK integration
│   ├── slack.py            # Slack Web API integration
│   └── base.py             # Platform adapter interface
├── output/
│   ├── table.py            # Terminal table output (rich)
│   ├── json.py             # Machine-readable export
│   └── report.py           # Markdown audit report generator
├── config/
│   ├── trusted_apps.yaml   # Known-good applications whitelist
│   └── thresholds.yaml     # Dormancy, cycling, and scope thresholds
└── groundskeeper.py        # CLI entry point
```

## Usage

```bash
# Scan all configured platforms
groundskeeper scan

# Scan specific platform
groundskeeper scan --platform github

# Show only flagged grants
groundskeeper scan --flagged

# Generate audit report
groundskeeper report --output audit-2026-03.md

# Revoke a specific grant (interactive confirmation)
groundskeeper revoke --platform github --app "ChatGPT Codex Connector"

# Continuous monitoring (check every 24h, alert on new grants)
groundskeeper watch --interval 24h
```

### Example Output

```
┌─────────────────────────────────┬──────────┬─────────────────────────┬───────────┬────────────┐
│ App                             │ Platform │ Scope                   │ Last Used │ Flags      │
├─────────────────────────────────┼──────────┼─────────────────────────┼───────────┼────────────┤
│ ChatGPT Codex Connector         │ GitHub   │ code(rw), actions(rw),  │ 1h ago    │ ⚠ BLANKET  │
│   openai                        │          │ issues(rw), PRs(rw),    │           │ ⚠ PHANTOM  │
│                                 │          │ workflows(rw)           │           │ ⚠ SPLIT    │
├─────────────────────────────────┼──────────┼─────────────────────────┼───────────┼────────────┤
│ Claude                          │ GitHub   │ code(rw), actions(rw)   │ 2w ago    │            │
│   anthropics                    │          │                         │           │            │
├─────────────────────────────────┼──────────┼─────────────────────────┼───────────┼────────────┤
│ Some Forgotten App              │ Google   │ drive(r), gmail(r)      │ 8mo ago   │ ⚠ DORMANT  │
│   unknown-dev                   │          │                         │           │ ⚠ UNKNOWN  │
└─────────────────────────────────┴──────────┴─────────────────────────┴───────────┴────────────┘

3 grants found · 2 flagged · 1 clean
```

## Configuration

```yaml
# config/thresholds.yaml
dormancy_days: 90           # Flag apps unused for this long
phantom_cycle_hours: 24     # Flag token refresh faster than this with no user activity
max_blanket_repos: 5        # Flag "all repos" if account has more than this many

# config/trusted_apps.yaml
trusted:
  github:
    - developer: "anthropics"
    - developer: "github"
  google:
    - developer: "google.com"
```

## Authentication

Groundskeeper needs read access to each platform's permission and audit APIs. It stores credentials locally and never phones home.

- **GitHub** — Personal Access Token with `read:org`, `read:audit_log`, `read:user` scope
- **Google** — OAuth2 credentials with Admin SDK read scope
- **Slack** — User token with `admin.apps:read` scope

All credentials are stored in `~/.groundskeeper/credentials.yaml` (encrypted at rest via system keyring) or passed via environment variables.

## Philosophy

This tool exists because permission UX is a security vulnerability wearing a cardigan.

Platforms make authorization one click and revocation a treasure hunt. They split grants across multiple pages and call them different things. They default to maximum scope and trust you to notice. They maintain persistent credential heartbeats against your accounts and call it "convenience."

Sovereignty means verifying who has the keys — not trusting that the locksmith's filing system is in your interest.

Groundskeeper is part of the [Digital Tractor](https://github.com/kase1111-hash) ecosystem: tools for people who own their infrastructure rather than renting it.

## License

MIT

## Contributing

Issues and PRs welcome. If you've been surprised by a phantom permission grant on a platform Groundskeeper doesn't cover yet, open an issue with the platform name and relevant API documentation. The adapter interface in `platforms/base.py` is designed to make new platforms straightforward to add.
