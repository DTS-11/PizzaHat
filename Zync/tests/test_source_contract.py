"""Static contract checks for the Discord-only transformation."""

from __future__ import annotations

import re
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
PYTHON_FILES = [
    path
    for path in SOURCE_ROOT.rglob("*.py")
    if ".venv" not in path.parts and "tests" not in path.parts
]

FORBIDDEN_TOKENS = (
    "pizzahat",
    "PizzaHat",
    "Your Ultimate Discord Companion",
)
FORBIDDEN_IMPORT = "from utils.custom_checks import _tier_cache"
LEGACY_SQL = re.compile(
    r"\b(FROM|INTO|UPDATE|DELETE\s+FROM|JOIN|TABLE)\s+(warnlogs|ticket_logs|guild_logs|logs_config)\b",
    re.IGNORECASE,
)


def _contents(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_no_legacy_branding_or_tier_cache_imports() -> None:
    offenders: list[str] = []
    for path in PYTHON_FILES:
        text = _contents(path)
        for token in FORBIDDEN_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(SOURCE_ROOT)}: {token}")
        if FORBIDDEN_IMPORT in text:
            offenders.append(f"{path.relative_to(SOURCE_ROOT)}: {FORBIDDEN_IMPORT}")
    assert not offenders, "\n".join(offenders)


def test_no_legacy_database_tables_in_source_sql() -> None:
    offenders: list[str] = []
    for path in PYTHON_FILES:
        for match in LEGACY_SQL.finditer(_contents(path)):
            offenders.append(
                f"{path.relative_to(SOURCE_ROOT)}: {match.group(0)}"
            )
    assert not offenders, "\n".join(offenders)
