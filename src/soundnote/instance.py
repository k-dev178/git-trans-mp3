"""Nonblocking OS locks, released automatically if a process exits."""

import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class InstanceLock:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.stream = (directory / "server.lock").open("a+b")
        # Windows locks a byte range; ensure byte zero exists before locking it.
        if os.fstat(self.stream.fileno()).st_size == 0:
            self.stream.write(b"\0")
            self.stream.flush()
        self.locked = False

    def acquire(self):
        if self.locked:
            return True
        try:
            if os.name == "nt":
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        self.locked = True
        return True

    def close(self):
        # Closing the handle releases the lock on both platforms.
        self.stream.close()
        self.locked = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
