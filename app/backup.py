"""Create a consistent SQLite backup without stopping the application."""

import os
import sqlite3
import sys
from pathlib import Path

from .config import Bootstrap


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError("The backup destination must differ from the live database.")
    # Exclusive creation avoids accidentally overwriting a prior backup or following a symlink.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.backup /data/unique-backup-name.db")
    backup(Bootstrap().database_path, sys.argv[1])
    print("Database backup complete. Preserve the matching encryption key separately.")
