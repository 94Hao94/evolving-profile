"""Cross-process lock primitives; Windows must never silently skip exclusion.

flock is an FD-compatible bridge for existing callers. New code uses file_lock.
Windows conservatively serializes shared locks as exclusive one-byte locks.
"""
from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import time

LOCK_SH,LOCK_EX,LOCK_NB,LOCK_UN=1,2,4,8


def _windows_flock(fd, operation):
    import msvcrt
    position=os.lseek(fd,0,os.SEEK_CUR)
    try:
        if os.fstat(fd).st_size==0:
            os.write(fd,b'\0')
        os.lseek(fd,0,os.SEEK_SET)
        if operation & LOCK_UN:
            msvcrt.locking(fd,msvcrt.LK_UNLCK,1);return
        while True:
            try:
                msvcrt.locking(fd,msvcrt.LK_NBLCK,1);return
            except OSError as exc:
                if exc.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):raise
                if operation & LOCK_NB:raise BlockingIOError(errno.EAGAIN,'lock_busy') from None
                time.sleep(0.01)
    finally:os.lseek(fd,position,os.SEEK_SET)


def flock(fd, operation):
    fd=fd if isinstance(fd,int) else fd.fileno()
    if os.name=='nt':return _windows_flock(fd,operation)
    import fcntl
    return fcntl.flock(fd,operation)


@contextmanager
def file_lock(path, *, shared=False, timeout_seconds=10.0):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    flags=os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags,0o600);locked=False
    start=time.monotonic()
    try:
        while True:
            try:
                flock(fd,(LOCK_SH if shared else LOCK_EX)|LOCK_NB);locked=True;break
            except BlockingIOError:
                if timeout_seconds is not None and time.monotonic()-start>=timeout_seconds:
                    raise TimeoutError('lock_busy') from None
                time.sleep(0.01)
        yield
    finally:
        if locked:flock(fd,LOCK_UN)
        os.close(fd)


def atomic_replace_bytes(path,payload,*,expected_sha256=None,check_revision=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with file_lock(path.with_name(path.name+'.lock')):
        if path.is_symlink():raise ValueError('symlink_target_rejected')
        previous=path.read_bytes() if path.exists() else None
        actual=hashlib.sha256(previous).hexdigest() if previous is not None else None
        if check_revision and actual!=expected_sha256:raise ValueError('revision_conflict')
        mode=stat.S_IMODE(path.stat().st_mode) if previous is not None else 0o600
        fd,temp=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(payload);f.flush();os.fsync(f.fileno())
            os.chmod(temp,mode);os.replace(temp,path)
        finally:
            try:os.unlink(temp)
            except FileNotFoundError:pass
    return hashlib.sha256(payload).hexdigest()
