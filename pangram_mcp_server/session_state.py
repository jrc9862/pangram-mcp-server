"""Where the login lives on disk, and the record of when it was made.

Layout, with the profile path configurable and everything else beside it:

    ~/.pangram-mcp/
        profile/            Chromium persistent context
        cookies.json        pangram.com cookies exported at login
        source-state.json   written once a login succeeds

``source-state.json`` is the marker that a login finished. A profile directory
alone proves nothing: a headed login that was abandoned half-way leaves one.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from pangram_mcp_server.common_utils import (
    secure_mkdir,
    secure_write_text,
    utcnow_iso,
)

logger = logging.getLogger(__name__)

SOURCE_STATE_VERSION = 1


def canonical(path: str | Path) -> Path:
    """Expand ``~`` and resolve symlinks together, so the profile and its
    sidecar files can never end up in different directories."""
    return Path(path).expanduser().resolve()


def get_profile_dir() -> Path:
    from pangram_mcp_server.config import get_config

    return canonical(get_config().browser.user_data_dir)


def auth_root(profile_dir: Path | None = None) -> Path:
    return (profile_dir or get_profile_dir()).parent


def portable_cookie_path(profile_dir: Path | None = None) -> Path:
    return auth_root(profile_dir) / "cookies.json"


def source_state_path(profile_dir: Path | None = None) -> Path:
    return auth_root(profile_dir) / "source-state.json"


@dataclass
class SourceState:
    version: int
    created_at: str
    profile_path: str
    cookies_path: str


def write_source_state(profile_dir: Path | None = None) -> SourceState:
    profile_dir = profile_dir or get_profile_dir()
    state = SourceState(
        version=SOURCE_STATE_VERSION,
        created_at=utcnow_iso(),
        profile_path=str(profile_dir),
        cookies_path=str(portable_cookie_path(profile_dir)),
    )
    secure_mkdir(auth_root(profile_dir))
    secure_write_text(
        source_state_path(profile_dir), json.dumps(asdict(state), indent=2) + "\n"
    )
    return state


def load_source_state(profile_dir: Path | None = None) -> SourceState | None:
    """Return the login record, or None if it is missing or unreadable."""
    path = source_state_path(profile_dir)
    try:
        data = json.loads(path.read_text())
        return SourceState(**data)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Ignoring unreadable %s: %s", path, exc)
        return None


def profile_exists(profile_dir: Path | None = None) -> bool:
    profile_dir = profile_dir or get_profile_dir()
    return profile_dir.is_dir() and any(profile_dir.iterdir())


def has_saved_login(profile_dir: Path | None = None) -> bool:
    profile_dir = profile_dir or get_profile_dir()
    return load_source_state(profile_dir) is not None and profile_exists(profile_dir)


def profile_in_use(profile_dir: Path | None = None) -> bool:
    """Whether a Chromium process holds the profile right now.

    Chromium leaves ``SingletonLock`` as a symlink to ``host-pid``; a dangling
    one means the process is gone.
    """
    lock = (profile_dir or get_profile_dir()) / "SingletonLock"
    if not lock.is_symlink():
        return False
    target = os.readlink(lock)
    _, _, pid = target.rpartition("-")
    if not pid.isdigit():
        return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
