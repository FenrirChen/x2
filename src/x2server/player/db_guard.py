"""Coordinate WAL checkpoints with HTTP/admin writers on the same machine."""
from pathlib import Path
import os
import threading
import time

if os.name == 'posix':
    import fcntl
else:
    import msvcrt


class CheckpointGuard:
    def __init__(self, database):
        self._thread = threading.RLock()
        self._depth = 0
        self._file = Path(str(database) + '.checkpoint.lock').open('a+b')
        if self._file.tell() == 0:
            self._file.write(b'0')
            self._file.flush()

    def acquire(self, blocking=True):
        if not self._thread.acquire(blocking=blocking):
            return False
        if self._depth:
            self._depth += 1
            return True
        try:
            while True:
                try:
                    if os.name == 'posix':
                        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    else:
                        self._file.seek(0)
                        msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
                    self._depth = 1
                    return True
                except (BlockingIOError, PermissionError):
                    if not blocking:
                        self._thread.release()
                        return False
                    time.sleep(.01)
                except OSError as exc:
                    if getattr(exc, 'winerror', None) != 33:
                        raise
                    if not blocking:
                        self._thread.release()
                        return False
                    time.sleep(.01)
        except BaseException:
            self._thread.release()
            raise

    def release(self):
        self._depth -= 1
        try:
            if not self._depth:
                if os.name == 'posix':
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                else:
                    self._file.seek(0)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._thread.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()

    def close(self):
        self._file.close()
