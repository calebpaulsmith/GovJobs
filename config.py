"""Single source of truth for configuration. Reads `.env` via python-dotenv.

All other modules import `Config` and `load_config` from here. No module reads
`os.environ` directly. This keeps secrets in one place and makes config
swappable in tests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    def load_dotenv(*_a, **_kw):  # type: ignore[no-redef]
        return False


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Hints that mean "the user copied .env.example but didn't fill in real values".
_PLACEHOLDER_HINTS = ("your_", "@example.com", "_here")


def _value(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _maybe_secret(key: str) -> str | None:
    raw = _value(key)
    if not raw:
        return None
    lower = raw.lower()
    if any(h in lower for h in _PLACEHOLDER_HINTS):
        return None
    return raw


@dataclass(frozen=True)
class Config:
    usajobs_user_agent: str | None
    usajobs_authorization_key: str | None

    database_path: Path
    raw_data_path: Path
    processed_data_path: Path

    max_full_download_gb: float
    max_database_gb: float
    max_full_download_rows: int
    max_import_hours: float

    log_level: str
    log_file: Path

    @property
    def has_usajobs_credentials(self) -> bool:
        return bool(self.usajobs_user_agent and self.usajobs_authorization_key)


def load_config(root: Path = ROOT) -> Config:
    """Load configuration from environment / .env. Pure — no side effects."""
    return Config(
        usajobs_user_agent=_maybe_secret("USAJOBS_USER_AGENT"),
        usajobs_authorization_key=_maybe_secret("USAJOBS_AUTHORIZATION_KEY"),
        database_path=root / _value("DATABASE_PATH", "data/federal_jobs.sqlite"),
        raw_data_path=root / _value("RAW_DATA_PATH", "data/raw"),
        processed_data_path=root / _value("PROCESSED_DATA_PATH", "data/processed"),
        max_full_download_gb=float(_value("MAX_FULL_DOWNLOAD_GB", "5")),
        max_database_gb=float(_value("MAX_DATABASE_GB", "10")),
        max_full_download_rows=int(_value("MAX_FULL_DOWNLOAD_ROWS", "5000000")),
        max_import_hours=float(_value("MAX_IMPORT_HOURS", "8")),
        log_level=_value("LOG_LEVEL", "INFO"),
        log_file=root / _value("LOG_FILE", "data/app.log"),
    )
