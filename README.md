<h1 align="center">
  <img src="./Zync/assets/images/bot-logo.png" width="260" height="260" alt="Zync logo"><br>
  Zync
</h1>

<h4 align="center">Your Ultimate Discord Companion</h4>

<p align="center">
  <img src="https://img.shields.io/badge/discord.py-2.7.1-blue?style=flat" alt="discord.py 2.7.1">
  <img src="https://img.shields.io/badge/Python-3.10%2B-green?style=flat&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/uv-managed-purple?style=flat" alt="uv managed">
  <img src="https://github.com/DTS-11/Zync/actions/workflows/codeql-analysis.yml/badge.svg" alt="CodeQL">
</p>

## Info

[Zync](https://pizzahat.vercel.app) is a slash-first Discord bot built around a deterministic
**Trigger → Condition → Action** workflow engine, with moderation, safety, tickets, tags, role menus,
embed templates, logging, and staff utilities in one place.

The public command surface is slash commands. The bot mention (`@Zync`) remains as a text-command
fallback where Discord delivers message content; there is no custom prefix.

The project is open source for educational and development purposes. This README is for contributors;
start with [Development setup](#development-setup) and see [CONTRIBUTING.md](./CONTRIBUTING.md)
before opening a pull request.

## Features

### Workflow engine

- Create, list, toggle, and delete workflows with `/workflow`
- Five starter templates:
  - new-account raid shield
  - auto-responder
  - welcome and onboarding
  - starboard / highlight reel
  - timezone-aware scheduled reminder
- Triggers:
  - `member_join`
  - `message_create`
  - `reaction_add`
  - `role_update`
  - `schedule`
  - `safety_alert`
- Conditions:
  - `account_age_lt`
  - `contains_link`
  - `contains_text`
  - `has_role`
  - `channel_in`
  - `cooldown_sec`
  - `is_bot`
  - `emoji_is`
  - `reaction_count_gte`
  - `not_self_react`
- Actions:
  - `add_role`
  - `remove_role`
  - `send_embed`
  - `send_message`
  - `send_dm`
  - `timeout_member`
  - `open_ticket`
  - `log_channel`
- Strict schema validation in `utils/workflow_schema.py`
- Cached evaluation in `cogs_hidden/workflow_runner.py`
- Tier limits:
  - Free: 5 active workflows, 2 actions per workflow
  - Basic: 25 active workflows, 5 actions per workflow
  - Pro: unlimited

### Moderation and staff tools

- All staff tools live under one `/mod` group — `/mod ban`, `/mod kick`, `/mod timeout`, `/mod warn`, `/mod clear`, `/mod role`, `/mod channel`, `/mod logs`, and more
- Variants are parameters, not duplicate commands: `/mod ban targets:@a @b soft:true`, `/mod kick targets:...`, `/mod timeout duration:1h` (omit `duration` to remove), `/mod clear bot_only:true`
- Right-click Ban/Kick/Warn/Timeout user menus ask for a reason (and a validated duration for Timeout), then reuse the same command bodies as their slash equivalents
- Server insights with workflow analytics
- Configurable guild logging in `cogs_hidden/guild_logs.py`
- Anti-alt and automod command surfaces merged into `/antialt` and `/automod`
- Persistent safety listeners in `cogs_hidden/safety_hooks.py`, including `safety_alert` workflow triggers

### Community tools

- Ticket panels, persistent ticket buttons, and thread logs
- Button/dropdown role menus with persistent view registration
- Tags with create, edit, delete, list, info, and lookup
- Embed templates with preview and template linking for role menus and ticket panels
- Emoji management with `/emoji create`, `delete`, `info`, and `list`
- Image helpers are standalone `/emojify` and `/emojifyav`

### Information and command discovery

Top-level commands are kept deliberately short:

- `/help` — categorized, paginated browser with command selects, usage examples, and Back/Home buttons
- `/status`, `/premium`
- `/mod`, `/antialt`, `/automod`, `/emoji`, `/rolemenu`, `/tag`, `/template`, `/tickets`, `/workflow`
- `/emojify`, `/emojifyav`

General bot utilities (timezone, credits, invite, support, vote) live together under `/info`. `/help` builds its categories from the live command tree, so it never shows stale paths. Owner-only developer commands stay prefix-only via mention (`@Zync eval`, `@Zync reloadall`) and never enter the public slash menu.

During development, set `DEV_GUILD_ID` in `.env` to scope command syncs to one test server, or `SYNC_COMMANDS=0` to skip syncing entirely. See `Zync/.env.example`.

## Project layout

```txt
Zync/                     uv project root
  cogs/                   public command surfaces
  cogs_hidden/            listeners, runners, and persistent view registration
  core/                   bot bootstrap, database bootstrap, shared cog base
  utils/                  reusable UI components, embeds, validation, config, checks
  pyproject.toml          uv project metadata and dependency groups
  uv.lock                 locked dependency set
  .env.example            local environment template
README.md                 project overview and contributor guide
```

Reusable UI components live in `utils/ui.py`; `cogs_hidden/interactions.py` only registers persistent
views. There is no custom prefix system, and the bot does not request the Message Content privileged
intent. Slash commands work normally; message-content-based automod checks need that intent enabled
separately to be effective in guilds.

## Development setup

This section is for contributors. Use it to set up a local development environment; it is not a
deployment or self-hosting guide.

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Git
- PostgreSQL, only if you are working on database-backed behavior locally

### Clone and install

From the repository root:

```bash
git clone https://github.com/DTS-11/Zync.git
cd Zync/Zync
uv sync
```

`uv sync` reads `Zync/pyproject.toml` and `Zync/uv.lock`, creates `Zync/.venv`, and
installs runtime and dev dependencies. Add packages later from `Zync/` with:

```bash
uv add <package>
```

### Local environment

From `Zync/`, copy the environment template and fill in the values you need:

```bash
cp .env.example .env
```

`.env` is gitignored. `load_dotenv()` reads from the current working directory, so keep `.env` in
`Zync/` when using the project commands.

For automod work, create the gitignored `Zync/utils/bad_words.py` with a local list:

```python
BANNED_WORDS = [
    "example",
    "words",
    "to block",
]
```

### Checks

Run these from `Zync/` before opening a pull request:

```bash
uv run ruff check --select I .
uv run ruff format --check .
uv run python -m compileall cogs cogs_hidden core utils __main__.py
```

To apply import sorting and formatting first:

```bash
uv run ruff check --select I --fix .
uv run ruff format .
```

## Contributing

1. Read the [Code of Conduct](./CODE_OF_CONDUCT.md).
2. Fork the repository and create a focused branch.
3. Keep changes scoped:
   - public commands belong in `cogs/`
   - listeners/runners belong in `cogs_hidden/`
   - reusable components belong in `utils/`
4. New commands must be slash-accessible. Do not reintroduce a custom prefix.
5. Workflow changes must go through `utils/workflow_schema.py`; do not bypass validation.
6. The database schema lives only in `core/database.py`. Keep the bootstrap SQL additive and
   idempotent; do not add migration files.
7. Do not drop tables in bootstrap. Rebuild stale local databases manually if needed.
8. Run the checks above before opening a pull request.
9. Commit, push, and open a PR describing the behavior changed.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the short checklist.

## Links

- [Website](https://pizzahat.vercel.app)
- [Invite bot](https://discord.com/oauth2/authorize?client_id=860889936914677770&permissions=10432416312438&scope=bot)
- [Support server](https://discord.gg/WhNVDTF)
- [Source](https://github.com/DTS-11/Zync)
