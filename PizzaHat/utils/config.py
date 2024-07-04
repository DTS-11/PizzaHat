import os

from dotenv import load_dotenv

load_dotenv()


LOGS_CHANNEL = 980151632199299092  # channel for sending bot join/leave logs

TOKEN = os.getenv("BOT_TOKEN")  # bot token
TEST_BOT = os.getenv("TEST_BOT")  # test bot token (optional)
PG_URL = os.getenv("PG_URL")  # postgres connection url
TOPGG_TOKEN = os.getenv("DBL_TOKEN")  # top.gg token
DLIST_TOKEN = os.getenv("DLIST_AUTH")  # dlist.gg token


COG_EXCEPTIONS = [
    "AntiAltsConfig",
    "AutoModConfig",
    "Dev",
    "Events",
    "GuildLogs",
    "Help",
    "Jishaku",
]
