"""Environment-backed configuration.

Only deployment-level values live here.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# TOKENS
TOKEN = os.getenv("TOKEN")
TEST_BOT = os.getenv("TEST_BOT")
PG_URL = os.getenv("PG_URL")

# CHANNELS
LOGS_CHANNEL = 980151632199299092

# ROLES
STAFF_ROLE = 849669358316683284
PARTNER_ROLE = 972071921791410188
BOOSTER_ROLE = 782258520791449600
CONTRIBUTOR_ROLE = 950785470286163988

# LINKS
SUPPORT_SERVER = "https://discord.gg/WhNVDTF"
ADMIN_INVITE = "https://discord.com/oauth2/authorize?client_id=860889936914677770&permissions=8&scope=bot"
REG_INVITE = "https://discord.com/oauth2/authorize?client_id=860889936914677770&permissions=10432416312438&scope=bot"
REPO_LINK = "https://github.com/DTS-11/Lucent"
UPGRADE_URL = "https://lucentbot.app/premium"
TOPGG_VOTE = "https://top.gg/bot/860889936914677770/vote"
DLISTGG_VOTE = "https://discordlist.gg/bot/860889936914677770/vote"
WUMPUS_VOTE = "https://wumpus.store/bot/860889936914677770/vote"

# OTHERS
ANTIHOIST_CHARS = "!@#$%^&*()_+-=.,/?;:[]{}`~\"'\\|<>"
