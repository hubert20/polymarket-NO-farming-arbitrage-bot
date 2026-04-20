"""Load environment from app root and backend overrides."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def app_root() -> Path:
    """Next.js app root (parent of backend/)."""
    return Path(__file__).resolve().parent.parent.parent


def backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def bootstrap_env() -> Path:
    """Load backend/.env (wallet settings managed from dashboard)."""
    root = app_root()
    load_dotenv(backend_dir() / ".env")
    load_dotenv(root / ".env.local")
    return root
