import os
import stat

from pangram_mcp_server.session_state import (
    get_profile_dir,
    has_saved_login,
    load_source_state,
    portable_cookie_path,
    profile_in_use,
    source_state_path,
    write_source_state,
)
from pangram_mcp_server.setup import logout


def test_sidecars_sit_beside_the_profile(profile_dir):
    assert source_state_path(profile_dir).parent == profile_dir.parent
    assert portable_cookie_path(profile_dir).parent == profile_dir.parent


def test_source_state_round_trip(profile_dir):
    written = write_source_state(profile_dir)
    assert load_source_state(profile_dir) == written
    mode = stat.S_IMODE(source_state_path(profile_dir).stat().st_mode)
    assert mode == 0o600


def test_unreadable_source_state_is_none(profile_dir):
    source_state_path(profile_dir).write_text("{not json")
    assert load_source_state(profile_dir) is None


def test_saved_login_needs_record_and_profile(profile_dir):
    assert not has_saved_login(profile_dir)
    write_source_state(profile_dir)
    assert has_saved_login(profile_dir)


def test_dangling_singleton_lock_is_not_in_use(profile_dir):
    os.symlink("host-999999999", profile_dir / "SingletonLock")
    assert not profile_in_use(profile_dir)


def test_live_singleton_lock_is_in_use(profile_dir):
    os.symlink(f"host-{os.getpid()}", profile_dir / "SingletonLock")
    assert profile_in_use(profile_dir)


def test_logout_refuses_a_profile_it_did_not_create(profile_dir):
    message = logout()
    assert "Not deleting" in message
    assert profile_dir.exists()


def test_logout_deletes_its_own_profile(profile_dir):
    write_source_state(profile_dir)
    portable_cookie_path(profile_dir).write_text("[]")
    logout()
    assert not get_profile_dir().exists()
    assert not portable_cookie_path(profile_dir).exists()
    assert not source_state_path(profile_dir).exists()
