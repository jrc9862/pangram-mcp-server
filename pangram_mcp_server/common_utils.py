"""Small filesystem and time helpers."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def utcnow_iso() -> str:
    """Return the current UTC time as a compact ISO-8601 string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def secure_mkdir(path: Path, mode: int = 0o700) -> None:
    """Create a directory tree, applying *mode* to every directory it creates.

    ``Path.mkdir(parents=True, mode=...)`` applies the mode to the leaf only.
    """
    if path.exists() and not path.is_dir():
        raise NotADirectoryError(f"Path exists and is not a directory: {path}")
    missing: list[Path] = []
    p = path
    while not p.exists():
        missing.append(p)
        p = p.parent
    for part in reversed(missing):
        part.mkdir(mode=mode, exist_ok=True)


def secure_write_text(path: Path, content: str, mode: int = 0o600) -> None:
    """Write *content* atomically to a file only the owner can read."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
