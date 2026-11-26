"""Environment-backed configuration.

Only deployment-level values live here. Guild-specific IDs are stored in the
database, and out-of-scope integrations (bot lists, SaaS checkout) are absent.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# TOKENS
TOKEN = os.getenv("TOKEN")
TEST_BOT = os.getenv("TEST_BOT")
PG_URL = os.getenv("PG_URL")

# Optional runtime configuration
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0")) or None
UPGRADE_URL = os.getenv("UPGRADE_URL", "https://github.com/DTS-11/Zync")
SUPPORT_SERVER = os.getenv("SUPPORT_SERVER", "https://discord.gg/WhNVDTF")
ADMIN_INVITE = os.getenv("ADMIN_INVITE", "")
REG_INVITE = os.getenv("REG_INVITE", "")
REPO_LINK = "https://github.com/DTS-11/Zync"

ANTIHOIST_CHARS = "!@#$%^&*()_+-=.,/?;:[]{}`~\"'\\|<>"


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    return int(raw) if raw and raw.isdigit() else None


TEST_GUILD_ID = _optional_int("TEST_GUILD_ID")
