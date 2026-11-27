"""Structured logging configuration for the Lucent runtime.

Logging is configured explicitly from the entry point rather than at import
time. The file handler appends and rotates so restarts do not destroy history.
"""

from __future__ import annotations

import logging
import os
from logging.config import dictConfig
from pathlib import Path


def configure_logging() -> None:
    """Configure console and rotating file handlers once at process start."""

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"

    log_path = Path(os.getenv("LOG_FILE", "bot.log")).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {
                    "format": "%(levelname)-8s %(name)s: %(message)s",
                },
                "file": {
                    "format": (
                        "%(asctime)s %(levelname)-8s %(name)s "
                        "[%(module)s:%(lineno)d] %(message)s"
                    ),
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "console",
                    "level": level,
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "file",
                    "level": level,
                    "filename": str(log_path),
                    "maxBytes": int(os.getenv("LOG_MAX_BYTES", "5242880")),
                    "backupCount": int(os.getenv("LOG_BACKUPS", "3")),
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "lucent": {
                    "handlers": ["console", "file"],
                    "level": level,
                    "propagate": False,
                },
                "bot": {
                    "handlers": ["console", "file"],
                    "level": level,
                    "propagate": False,
                },
                "discord": {
                    "handlers": ["console", "file"],
                    "level": "INFO",
                    "propagate": False,
                },
            },
            "root": {"handlers": ["console", "file"], "level": level},
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the application namespace."""

    return logging.getLogger(
        f"lucent.{name}" if not name.startswith("lucent") else name
    )
