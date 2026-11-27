"""Static contract checks for the Discord-only transformation."""

from __future__ import annotations

import re
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SOURCE_ROOT.parent
PYTHON_FILES = [
    path
    for path in SOURCE_ROOT.rglob("*.py")
    if ".venv" not in path.parts and "tests" not in path.parts
]

# Constructed in parts so the contract itself does not contain the retired name.
OLD_BRAND = "zy" + "nc"
OLD_BRAND_RE = re.compile(re.escape(OLD_BRAND), re.IGNORECASE)
URI_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s<>\"'`]+")
SKIP_DIRS = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}

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
            offenders.append(f"{path.relative_to(SOURCE_ROOT)}: {match.group(0)}")
    assert not offenders, "\n".join(offenders)


def test_no_retired_brand_name_outside_urls() -> None:
    offenders: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parent.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in OLD_BRAND_RE.finditer(URI_RE.sub("", text)):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)}")
    assert not offenders, "\n".join(offenders)
