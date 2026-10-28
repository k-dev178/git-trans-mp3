"""Paths shared by source checkouts and standalone distributions."""

import os
from pathlib import Path
import sys

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[2]


def data_directory():
    override = os.environ.get("SOUNDNOTE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if not FROZEN:
        return ROOT / "data"
    return Path.home() / "Library/Application Support/Soundnote"


def native_directory():
    if FROZEN:
        return Path(sys._MEIPASS) / "native"
    return ROOT / "tools/native"
