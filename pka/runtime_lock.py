"""One supported server or offline maintenance command per data directory."""
from contextlib import contextmanager
import os
from pathlib import Path


@contextmanager
def data_lock(directory):
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / '.runtime.lock'
    # Keep the file in place: deleting an unlocked inode allows a second lock file
    # to be created while another process still has the original one open.
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('This data directory is in use. Stop KT Assistant before offline maintenance.') from None
        try:
            yield root
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
