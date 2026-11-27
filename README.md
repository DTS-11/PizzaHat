<h1 align="center">
  <img src="./lucent/assets/images/bot-logo.png" width="260" height="260" alt="Lucent logo"><br>
  Lucent
</h1>

<h4 align="center">Deterministic Discord operations and workflow automation</h4>

<p align="center">
  <img src="https://img.shields.io/badge/discord.py-2.7.1-blue?style=flat" alt="discord.py 2.7.1">
  <img src="https://img.shields.io/badge/Python-3.10%2B-green?style=flat&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/uv-managed-purple?style=flat" alt="uv managed">
  <img src="https://github.com/DTS-11/Lucent/actions/workflows/ci.yml/badge.svg" alt="CI">
</p>

## Info

Lucent is a mention-first Discord operations engine built around a deterministic
**Trigger → Condition → Action** workflow system. Daily commands use
`@Lucent <command> [arguments]`; the Discord picker is limited to `/help`, `/setup`,
`/view_setup`, `/status`, and a small set of context menus. It keeps moderation,
protection, tickets, events, and staff utilities in one Discord-only service.

There is no dashboard, visual editor, SaaS API, checkout, remote publishing, AI, or
analytics product in this repository. Owner-only developer commands stay prefix-only
through the bot mention and never enter the public slash menu.

### Message content capability

The Message Content privileged intent is deliberately **not** enabled. Mention
commands work because Discord delivers the content of messages that mention the bot.
Text-based AutoMod detectors (bad words, scam links, caps, invites, emoji/newline/
repeated-character spam), `contains_text`/`contains_link` workflow conditions,
message-content templates, and `{content}`/`from_message` placeholders are rejected
or skipped in code. Metadata-only modules and workflows remain available.

## Features

### Workflow engine

- Versioned, portable Trigger → Condition → Action definitions
- Triggers: `member_join`, `member_leave`, `message_create`, `message_delete`,
  `reaction_add`, `role_update`, `schedule`, `safety_alert`, `moderation_event`,
  `ticket_created`
- Deterministic condition evaluation with no arbitrary code execution
- Service-backed actions with permission and hierarchy checks
- Persisted execution history, cancellation, cooldown state, and loop protection
- Rate-limit-safe sequential execution with bounded 429 backoff
- `@Lucent workflow list`, `view`, `create`, `import`, `export`, `toggle`, `delete`, `templates`
- Guided Trigger → Conditions → Actions builder in `/setup`
- Strict validation through `workflows/schema.py` (re-exported by `utils/workflow_schema.py`)
- Tier limits:
  - Free: 5 active workflows, 2 actions per workflow
  - Basic: 25 active workflows, 5 actions per workflow
  - Pro: unlimited

### Moderation and protection

- Mention commands for ban, unban, kick, timeout, warn, clear, prune, slowmode,
  nick, lock, role, channel, logs, and insights
- Right-click Ban/Kick/Warn/Timeout/View Cases and message Delete/Warn Author menus
  reuse the same service layer
- Unique moderation casefiles for warnings and automated actions
- `@Lucent antialt` and `@Lucent automod` configuration surfaces plus `/setup` and
  `/view_setup`, all backed by one automation config store
- Safety detections dispatch `safety_alert` workflows; punishments create casefiles
- Durable scheduled tasks for temporary bans and raid lockdown restoration

### Server operations

- Ticket panels, persistent buttons, thread management, and transcripts
- Button/select role menus with persistent view registration
- Tags and embed templates as staff utilities
- Configurable guild logging with webhook delivery
- Persistent Discord views restored at startup

## Project layout

```txt
lucent/                   uv project root
  cogs/                   public command surfaces
  cogs_hidden/            listeners and persistent view registration
  core/                   bot lifecycle, database migrations, entitlements, logging
  services/               moderation, ticket, protection, logging, scheduler services
  workflows/              schema, registries, evaluator, engine, repository, runner
  migrations/             ordered SQL schema migrations
  utils/                  shared UI, embeds, formatting, config, checks
  tests/                  unit tests
  pyproject.toml          uv project metadata and dependency groups
  uv.lock                 locked dependency set
```

All schema changes live in ordered SQL files under `lucent/migrations/`. The runner
records applied versions in `schema_migrations` and applies each pending migration
inside a transaction at startup.

## Development setup

This section is for contributors. Use it to set up a local development environment;
it is not a hosted deployment guide.

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Git
- PostgreSQL, only if you are working on database-backed behavior locally

### Clone and install

From the repository root:

```bash
git clone https://github.com/DTS-11/Lucent.git
cd Lucent/lucent
uv sync --group dev
```

`uv sync` reads `lucent/pyproject.toml` and `lucent/uv.lock`, creates `lucent/.venv`, and
installs runtime and dev dependencies.

### Local environment

Configuration is read from environment variables. `python-dotenv` loads a local
`.env` from the current working directory when present.

The template in `lucent/.env.example` lists the supported values:

```txt
TOKEN=
CLIENT_SECRET=
PG_URL=""
DLIST_AUTH=
DBL_TOKEN=
```

Optional runtime flags are read directly from the environment when set. Do not commit
`.env`. The migration runner will create the schema on startup; there are no legacy imports.

### Checks

Run these from `lucent/` before opening a pull request:

```bash
uv run ruff check --select I --fix .
uv run ruff format .
uv run ruff check .
uv run python -m compileall -q cogs cogs_hidden core services utils workflows __main__.py
uv run pytest -q
```

## Single-instance operation

The Discord engine is designed for one process on a small VM or Raspberry Pi.
PostgreSQL is the only external service. Configure `PG_URL`, set intents in the
Discord developer portal, then start the process from the `lucent/` source root:

```bash
cd Lucent
uv run python __main__.py
```

Graceful shutdown closes the aiohttp session and the asyncpg connection pool. Logs
append to a rotating file instead of truncating on each restart.

## Contributing

1. Read the [Code of Conduct](./CODE_OF_CONDUCT.md).
2. Fork the repository and create a focused branch.
3. Keep changes scoped:
   - public commands belong in `cogs/`
   - listeners belong in `cogs_hidden/`
   - business rules belong in `services/`
   - workflow primitives belong in `workflows/`
   - reusable presentation helpers belong in `utils/`
4. New daily commands belong in the mention command tree; keep the slash picker limited to discovery and setup entry points.
5. Workflow changes must go through `workflows/schema.py`; do not bypass validation.
6. Database schema changes belong in ordered SQL files under `lucent/migrations/`.
7. Apply migrations with the migration runner at startup; do not mutate schema ad hoc in cogs.
8. Run the checks above before opening a pull request.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the short checklist.

## Links

- [Source](https://github.com/DTS-11/Lucent)
- [Support server](https://discord.gg/WhNVDTF)
