"""
Centralized filesystem paths and environment resolution for Pico.
Guarantees clean portability across Android Termux, Linux, macOS, Docker, and CI runners.
"""

from __future__ import annotations
import os
from pathlib import Path


def get_pico_home() -> Path:
    """Returns the effective base user home directory.
    
    1. Checks PICO_HOME environment variable (override).
    2. If running under Android Termux, prefers /data/data/com.termux/files/home.
    3. Falls back to standard Path.home().
    """
    env_home = os.environ.get("PICO_HOME")
    if env_home:
        return Path(env_home).resolve()

    termux_home = Path("/data/data/com.termux/files/home")
    if termux_home.exists() and termux_home.is_dir():
        return termux_home

    return Path.home()


def get_pico_dir() -> Path:
    """Returns ~/.pico configuration directory, ensuring it exists."""
    pico_dir = get_pico_home() / ".pico"
    pico_dir.mkdir(parents=True, exist_ok=True)
    return pico_dir


def get_default_db_path() -> str:
    """Returns the default SQLite database path for Pico chat & state."""
    db_env = os.environ.get("PICO_DB_PATH")
    if db_env:
        return db_env

    # Prefer repository root db if running from repo, otherwise ~/.pico/pico_chat.db
    repo_db = Path(__file__).resolve().parent / "pico_chat.db"
    if repo_db.parent.exists():
        return str(repo_db)
    return str(get_pico_dir() / "pico_chat.db")
