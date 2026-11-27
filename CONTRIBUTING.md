# Contributing to Lucent

Thanks for helping improve Lucent. Please read the [Code of Conduct](./CODE_OF_CONDUCT.md) before
opening a pull request.

## Getting started

1. Fork the repository.
2. Create a focused branch, e.g. `fix/workflow-cooldown` or `feature/ticket-export`.
3. From `lucent/`, copy the environment template and fill in the values you need:

   ```bash
   cp .env.example .env
   ```

   `.env` is gitignored. `load_dotenv()` reads from the current working directory, so keep `.env` in
   `lucent/` when using the project commands.

4. Install dependencies with uv from `lucent/`:

   ```bash
   uv sync
   ```

5. If you are working on automod, create the gitignored `lucent/utils/bad_words.py` with a local
   `BANNED_WORDS` list.
6. The repo root has a `.venv` link to `lucent/.venv`, plus `cogs`, `cogs_hidden`, `core`, and
   `utils` links into `lucent/`. This lets editors and language servers discover the environment and
   first-party imports from the repository root. The link is gitignored; recreate it with
   `ln -s lucent/.venv .venv` if it is missing. If your editor asks for an interpreter, choose
   `lucent/.venv/bin/python`. Reopen or reload the project after `uv sync` if imports still appear
   unresolved.
7. Make your changes and keep them scoped to the feature or bug.

## Project conventions

- Every Python module starts with a module-level docstring. Use the same concise
  summary-plus-detail style as `utils/workflow_schema.py`.
- Public commands live in `lucent/cogs/`.
- Listeners, runners, and persistent-view registration live in `lucent/cogs_hidden/`.
- Reusable components live in `lucent/utils/`.
- New daily commands belong in the mention command tree; keep the slash picker limited to discovery
  and setup entry points.
- The bot does not request the Message Content privileged intent. Avoid features that require reading
  raw guild message content unless the change explicitly addresses that limitation.
- Workflow payloads must pass through `utils/workflow_schema.py`. Do not bypass validation or tier
  limits in the runner or command layer.
- Database schema is defined only in `core/database.py`:
  - keep bootstrap SQL additive and idempotent
  - do not add numbered migration files
  - never drop tables in bootstrap
  - rebuild stale local databases manually if needed

## Checks

Before opening a pull request, run from `lucent/`:

```bash
uv run ruff check --select I --fix .
uv run ruff format .
uv run python -m compileall cogs cogs_hidden core utils __main__.py
uv run ruff check --select F821,F811,F402,F632 .
```

If you changed cogs, also load all extensions in a smoke test with `bot.db` set to `None` and
`bot.tree.sync` stubbed, so no network or database connection is needed.

## Pull requests

- Describe what changed and why.
- Mention any manual database migration required.
- Include the commands you ran to verify the change.
- Link related issues where applicable.
- Keep credits, license, and attribution intact.

## Notes

Lucent is open source for educational and development purposes. Keep credits, license, and
attribution intact. Do not reuse the Lucent name or logo in derivative bots.
