"""Check that the installed or bundled Qt runtime is available."""

import importlib.util


def ensure_qt():
    return importlib.util.find_spec("PySide6") is not None
