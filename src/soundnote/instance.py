"""Nonblocking OS locks, released automatically if a process exits."""

import fcntl
from pathlib import Path


class InstanceLock:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.stream = (directory / "server.lock").open("a+b")
        self.locked = False

    def acquire(self):
        try:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        self.locked = True
        return True

    def close(self):
        self.stream.close()
        self.locked = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
