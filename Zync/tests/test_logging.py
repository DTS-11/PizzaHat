from __future__ import annotations

import logging

from core.logging import configure_logging, get_logger


def test_configure_logging_uses_app_namespace(tmp_path, monkeypatch) -> None:
    log_file = tmp_path / "nested" / "zync.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))

    configure_logging()

    assert log_file.parent.exists()
    assert get_logger("bot").name == "zync.bot"
    assert get_logger("zync.engine").name == "zync.engine"
    assert logging.getLogger("discord").handlers


def test_invalid_level_falls_back_to_info(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "zync.log"))
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")

    configure_logging()

    assert logging.getLogger("zync").level == logging.INFO
