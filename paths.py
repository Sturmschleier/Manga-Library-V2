"""
paths.py
Ermittelt das Verzeichnis, in dem Datendateien (Datenbank, Google-
Zugangsdaten) abgelegt werden.

Wichtig für die spätere .exe: Wird die Anwendung mit PyInstaller (--onefile)
gebündelt, zeigt `__file__` zur Laufzeit auf einen temporären
Entpackungsordner, der nach dem Beenden wieder gelöscht wird. Damit die
Datenbank und die Google-Zugangsdaten dauerhaft neben der .exe erhalten
bleiben, wird in diesem Fall stattdessen der Ordner von `sys.executable`
verwendet.

In der Android-App (build_apk.py) liegt der Programmcode in einem Ordner,
der bei jedem Update ersetzt wird. Die Daten kommen dort in den privaten
Datenordner der App, den Flet in FLET_APP_STORAGE_DATA nennt.
"""

import os
import sys
from pathlib import Path


def is_android() -> bool:
    return hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ


def base_dir() -> Path:
    if is_android() and os.environ.get("FLET_APP_STORAGE_DATA"):
        path = Path(os.environ["FLET_APP_STORAGE_DATA"])
        path.mkdir(parents=True, exist_ok=True)
        return path
    if getattr(sys, "frozen", False):
        # Als PyInstaller-exe gebündelt: Ordner der .exe-Datei verwenden
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
