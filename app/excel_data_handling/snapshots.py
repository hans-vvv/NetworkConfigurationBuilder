from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.domain.file_locations import EXCEL_LOC, PRODUCTION_DB_LOC

WB_NAME = EXCEL_LOC.location
DB_NAME = PRODUCTION_DB_LOC.location


def _snapshot_paths():
    """
    Resolve the source workbook path, source database path, and snapshot base directory.

    Paths are resolved relative to the repository root, derived from this module's
    location. The snapshot base directory is created under the database file's
    parent directory as ``state_snapshots``.

    Returns
    -------
    tuple[pathlib.Path, pathlib.Path, pathlib.Path]
        A tuple containing:
        - path to the source Excel workbook
        - path to the source database
        - path to the snapshot base directory
    """
    repo_root = Path(__file__).resolve().parents[2]

    excel_src = repo_root / WB_NAME          
    db_src = repo_root / DB_NAME            

    base = db_src.parent / "state_snapshots"
    return excel_src, db_src, base


def snapshot_latest() -> None:
    """
    Save the current workbook and database as the latest successful snapshot.

    The snapshot layout is:

    - ``state_snapshots/latest`` for the most recent successful state
    - ``state_snapshots/history/<timestamp>`` for the previously stored latest state

    If a latest snapshot already exists, it is first archived into the history
    directory using a UTC timestamp. The current workbook and database are then
    copied into ``latest``.

    Returns
    -------
    None
    """
    excel_src, db_src, base = _snapshot_paths()

    latest = base / "latest"
    history = base / "history"
    latest.mkdir(parents=True, exist_ok=True)
    history.mkdir(parents=True, exist_ok=True)

    # archive current latest (if present)
    has_existing = (latest / excel_src.name).exists() or (latest / db_src.name).exists()
    if has_existing:
        ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        arch = history / ts
        arch.mkdir(parents=True, exist_ok=True)

        for fname in (excel_src.name, db_src.name):
            p = latest / fname
            if p.exists():
                shutil.move(str(p), str(arch / fname))

    # write new latest
    shutil.copy2(excel_src, latest / excel_src.name)
    shutil.copy2(db_src, latest / db_src.name)

def snapshot_failed() -> None:
    """
    Save the current workbook and database as a failed-run snapshot.

    Failed snapshots are stored under
    ``state_snapshots/failed/<timestamp>`` to preserve the exact input and
    database state associated with an unsuccessful run for later troubleshooting.

    Returns
    -------
    None
    """
    excel_src, db_src, base = _snapshot_paths()

    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    dst = base / "failed" / ts
    dst.mkdir(parents=True, exist_ok=True)

    shutil.copy2(excel_src, dst / excel_src.name)
    shutil.copy2(db_src, dst / db_src.name)
