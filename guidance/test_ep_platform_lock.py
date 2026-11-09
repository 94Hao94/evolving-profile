import hashlib
import multiprocessing
import os
import time
from pathlib import Path
import pytest


def _hold(path, ready):
    from ep_platform_lock import file_lock
    with file_lock(Path(path)):
        ready.set();time.sleep(20)


def test_cross_process_mutual_exclusion_and_process_exit_releases_lock(tmp_path):
    from ep_platform_lock import file_lock
    ctx=multiprocessing.get_context('spawn');ready=ctx.Event()
    p=ctx.Process(target=_hold,args=(str(tmp_path/'lock'),ready));p.start()
    try:
        assert ready.wait(5)
        with pytest.raises(TimeoutError):
            with file_lock(tmp_path/'lock',timeout_seconds=0):pass
    finally:p.terminate();p.join(5)
    with file_lock(tmp_path/'lock',timeout_seconds=1):pass


def test_exception_releases_lock(tmp_path):
    from ep_platform_lock import file_lock
    with pytest.raises(ValueError):
        with file_lock(tmp_path/'lock'):raise ValueError('expected')
    with file_lock(tmp_path/'lock',timeout_seconds=0):pass


def test_timeout_preserves_owner_lock(tmp_path):
    from ep_platform_lock import file_lock
    lock=tmp_path/'lock'
    with file_lock(lock):
        with pytest.raises(TimeoutError):
            with file_lock(lock,timeout_seconds=0.02):pass
        assert lock.exists()


def test_failed_replace_keeps_old_bytes(tmp_path,monkeypatch):
    import ep_platform_lock as mod
    p=tmp_path/'data';p.write_bytes(b'old')
    def fail(*args):raise PermissionError('occupied')
    monkeypatch.setattr(mod.os,'replace',fail)
    with pytest.raises(PermissionError):mod.atomic_replace_bytes(p,b'new',check_revision=False)
    assert p.read_bytes()==b'old'


def test_compare_and_replace_conflict(tmp_path):
    from ep_platform_lock import atomic_replace_bytes
    p=tmp_path/'data'
    first=atomic_replace_bytes(p,b'first')
    assert first==hashlib.sha256(b'first').hexdigest()
    with pytest.raises(ValueError,match='revision_conflict'):atomic_replace_bytes(p,b'other')
    with pytest.raises(ValueError,match='revision_conflict'):atomic_replace_bytes(p,b'other',expected_sha256='0'*64)
    atomic_replace_bytes(p,b'second',expected_sha256=first)
    assert p.read_bytes()==b'second'


def test_windows_backend_has_no_unlocked_fallback(tmp_path):
    import ep_platform_lock as mod
    if os.name=='nt':
        with mod.file_lock(tmp_path/'native-lock',timeout_seconds=0):pass
    else:
        with (tmp_path/'lock').open('a+b') as f:
            with pytest.raises(ImportError):mod._windows_flock(f.fileno(),mod.LOCK_EX|mod.LOCK_NB)


def test_symlink_target_rejected(tmp_path):
    from ep_platform_lock import atomic_replace_bytes
    p=tmp_path/'real';p.write_bytes(b'old');link=tmp_path/'link'
    try:link.symlink_to(p)
    except OSError:pytest.skip('symlink unavailable')
    with pytest.raises(ValueError):atomic_replace_bytes(link,b'changed',check_revision=False)
    assert p.read_bytes()==b'old'
