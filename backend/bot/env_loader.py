"""Load environment from the project root `.env` only."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def app_root() -> Path:
    """Monorepo root (parent of backend/)."""
    return Path(__file__).resolve().parent.parent.parent


def backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def env_path() -> Path:
    """Single env file at project root — shared by backend and Next.js dashboard."""
    return app_root() / ".env"


def bootstrap_env() -> Path:
    """Load root `.env` before any bot or dashboard code reads os.environ."""
    root = app_root()
    load_dotenv(env_path())
    return root
