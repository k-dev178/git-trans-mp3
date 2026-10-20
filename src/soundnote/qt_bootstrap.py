"""Use the project's Qt package, or a compatible Qt runtime already on this Mac."""

import importlib.util
from pathlib import Path
import sys


def ensure_qt():
    if importlib.util.find_spec("PySide6") is not None:
        return True
    # Qt and Shiboken use Python's stable ABI. Existing Conda runtimes can be
    # reused without copying packages or changing those environments.
    roots = [Path("/opt/homebrew/Caskroom/miniconda/base/envs"),
             Path.home() / "miniconda3/envs", Path.home() / "anaconda3/envs"]
    for root in roots:
        for packages in sorted(root.glob("*/lib/python3.*/site-packages")):
            if not (packages / "PySide6/QtCore.abi3.so").is_file() or not (packages / "shiboken6").is_dir():
                continue
            sys.path.append(str(packages))
            try:
                from PySide6 import QtCore, QtWidgets
                return True
            except ImportError:
                sys.path.remove(str(packages))
    return False
