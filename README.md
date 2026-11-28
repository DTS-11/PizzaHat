<h1 align="center">
  <img src="./lucent/assets/images/bot-logo.png" width="180" height="180" alt="Lucent logo"><br>
  Lucent
</h1>

<p align="center"><strong>Your server, on autopilot.</strong></p>
<p align="center">Automate the boring parts of Discord with custom rules, welcome flows, and built-in anti-alt &amp; automod protection. Fast, reliable, and zero bloat.</p>

<p align="center">
  <img src="https://img.shields.io/badge/discord.py-2.7.1-blue?style=flat" alt="discord.py 2.7.1">
  <img src="https://img.shields.io/badge/Python-3.10%2B-green?style=flat&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/uv-managed-purple?style=flat" alt="uv managed">
  <img src="https://github.com/DTS-11/Lucent/actions/workflows/ci.yml/badge.svg" alt="CI">
</p>

<p align="center">
  <a href="https://discord.gg/WhNVDTF">💬 Support</a> ·
  <a href="https://github.com/DTS-11/Lucent">⭐ Source code</a>
</p>

## • What is Lucent?

- 🛡️ A Discord bot for moderation, server protection, tickets, and staff tools.
- ⚙️ Automations built with **Trigger → Condition → Action** workflows.
- 💬 Daily commands are mention-first: `@Lucent <command> [arguments]`.
- ✨ Use `/help` to explore commands and `/setup` to configure Lucent in your server.

## • Features

- 🔨 **Moderation** — ban, kick, timeout, warn, message cleanup, role and channel tools.
- 🧾 **Case history** — review warnings and moderation actions with searchable case IDs.
- 🛡️ **Server protection** — Anti-Alt checks and configurable AutoMod modules.
- ⚡ **Workflows** — automate joins, schedules, safety alerts, moderation events, and tickets.
- 🎫 **Ticket tools** — persistent panels, private threads, transcripts, and staff tracking.
- 🎭 **Role menus** — let members assign roles through buttons and select menus.
- 📋 **Server logs** — choose which events Lucent records in your log channel.
- 🏷️ **Staff utilities** — tags, embed templates, and server emoji management.
- 🖱️ **Quick actions** — moderate members and messages from Discord’s right-click menus.

## • Get started

1. Add Lucent to your server.
2. Run `/setup` and choose the features and channels you want to configure.
3. Use `@Lucent help` for commands, examples, and usage details.
4. Run `/view_setup` any time to review your server configuration.

### Command examples

```text
@Lucent ban @member spam
@Lucent timeout @member 1h repeated spam
@Lucent workflow list
```

## • Plans

- 🆓 **Free** — 5 active workflows, up to 2 actions per workflow.
- 💠 **Basic** — 25 active workflows, up to 5 actions per workflow.
- 🚀 **Pro** — unlimited workflows and access to Pro-gated features.

Use `@Lucent premium` to check the tier enabled for your server.

## • Discord permission note

- 🔓 Lucent requests the privileged Message Content intent for text-based protection and workflows.
- ✅ Enable it for the application in the Discord Developer Portal.
- ⚠️ Without the portal toggle, the bot cannot connect; text-scanning AutoMod and content workflows need it.

## • Run locally

- 🐍 Python 3.10+ and [uv](https://docs.astral.sh/uv/) are required.
- 🗄️ PostgreSQL is required for database-backed features.
- 📦 Install dependencies from the project directory:

  ```bash
  cd lucent
  uv sync --group dev
  ```

- 🔐 Copy `.env.example` to `.env` and add your bot token and database URL.
- ▶️ Start Lucent from `lucent/` with `uv run python __main__.py`.
- 🧑‍💻 See [CONTRIBUTING.md](./CONTRIBUTING.md) for development notes.

## • Links

- 💬 [Support server](https://discord.gg/WhNVDTF)
- 📚 [Source code](https://github.com/DTS-11/Lucent)
- 🤝 [Contributing](./CONTRIBUTING.md)
