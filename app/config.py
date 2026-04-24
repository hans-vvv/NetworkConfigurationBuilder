from __future__ import annotations

import os
from pathlib import Path


def get_database_url() -> str:
    """
    Returns the database URL from env, or a deterministic default.
    Default: sqlite file at repo_root/app/app.db
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    app_dir = Path(__file__).resolve().parents[1]  # this is /app
    db_path = app_dir / "app.db"

    return f"sqlite:///{db_path.as_posix()}"