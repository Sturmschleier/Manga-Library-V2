"""
build_apk.py
Baut die Android-App MangaLibraryV2.apk mit "flet build apk" - wird von
build_apk.bat in der Build-Umgebung .venv-build aufgerufen (dieselben
festen Versionen wie für die exe, siehe requirements-build.txt).

Ablauf:
1. Zwischenordner .apk-src anlegen, der NUR den Programmcode, das Icon
   und pyproject.toml enthält. So landen weder die eigene Datenbank,
   config.json, covers/, LOG/, BACKUP/ noch Google-Zugangsdaten
   (credentials.json, token.json) in der APK.
2. "flet build apk" aus diesem Ordner; Paketliste, App-Name und
   Berechtigungen stehen in pyproject.toml ([project], [tool.flet]).
   Versionsname und -nummer kommen aus appinfo.VERSION.
3. Die fertige APK nach dist/MangaLibraryV2.apk kopieren.

Flutter, JDK 17, Android SDK und alle Caches lädt Flet beim ersten Lauf
herunter (mehrere GB). Sie kommen nach TOOLS_DIR statt ins Windows-Profil
auf C: - standardmäßig derselbe Ordner wie bei der Anime-Liste, damit
beide Projekte die Werkzeuge teilen. Ein anderer Ort: Umgebungsvariable
MANGALIB_ANDROID_TOOLS.

Voraussetzung unter Windows: Entwicklermodus (Einstellungen → System →
Für Entwickler), sonst darf Flutter keine symbolischen Links anlegen.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from appinfo import VERSION

ROOT = Path(__file__).resolve().parent
SRC = ROOT / ".apk-src"
OUT = ROOT / ".apk-out"     # bewusst außerhalb von .apk-src - sonst würde die vorige APK mit eingepackt
DIST_APK = ROOT / "dist" / "MangaLibraryV2.apk"
TOOLS_DIR = Path(os.environ.get("MANGALIB_ANDROID_TOOLS") or r"E:\Claude\.android-build")

FLET_BUILD_DIR = "build"   # legt "flet build" im Quellordner an - wird nicht mit eingepackt

# Nur für den PC bzw. den Build - gehört nicht in die App
EXCLUDED_MODULES = {"build_exe.py", "build_apk.py", "drive_sync.py"}


def build_number(version: str) -> int:
    """Fortlaufende Versionsnummer für Android (muss bei jedem Update
    steigen): 2.0.3 -> 20003, 2.1.0 -> 20100."""
    parts = [int(p) for p in version.split(".")[:3]] + [0, 0]
    major, minor, patch = parts[:3]
    return major * 10000 + minor * 100 + patch


def stage() -> None:
    """Füllt .apk-src mit Programmcode, Icon und pyproject.toml. Der
    Unterordner build/ (Flutter-Projekt und Zwischenstände von "flet build")
    bleibt stehen: Er macht spätere Builds deutlich schneller, und ein noch
    laufender Gradle-Hintergrundprozess hält dort Dateien offen."""
    SRC.mkdir(exist_ok=True)
    for child in SRC.iterdir():
        if child.name == FLET_BUILD_DIR:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (SRC / "ui").mkdir()
    (SRC / "assets").mkdir()
    for path in ROOT.glob("*.py"):
        if path.name not in EXCLUDED_MODULES:
            shutil.copy2(path, SRC / path.name)
    for path in (ROOT / "ui").glob("*.py"):
        shutil.copy2(path, SRC / "ui" / path.name)
    shutil.copy2(ROOT / "pyproject.toml", SRC / "pyproject.toml")
    # App-Icon: Flet erwartet assets/icon.png (siehe assets/make_icon.py)
    shutil.copy2(ROOT / "assets" / "MangaLibraryV2.png", SRC / "assets" / "icon.png")


def tool_env() -> dict:
    """Umgebung, die alle Downloads und Caches nach TOOLS_DIR lenkt - gilt
    nur für diesen Build, das Windows-Profil bleibt unverändert."""
    home = TOOLS_DIR / "home"
    paths = {
        "USERPROFILE": home,
        "HOME": home,
        "APPDATA": home / "AppData" / "Roaming",
        "LOCALAPPDATA": home / "AppData" / "Local",
        "TEMP": TOOLS_DIR / "tmp",
        "TMP": TOOLS_DIR / "tmp",
        "GRADLE_USER_HOME": TOOLS_DIR / "gradle",
        "PUB_CACHE": TOOLS_DIR / "pub-cache",
        "ANDROID_USER_HOME": home / ".android",
        "FLET_CACHE_DIR": TOOLS_DIR / "flet-cache",
        "PIP_CACHE_DIR": TOOLS_DIR / "pip-cache",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, **{k: str(v) for k, v in paths.items()})
    env["GRADLE_OPTS"] = f"-Duser.home={home}"
    return env


def main() -> int:
    print(f"Bereite den Programmcode in {SRC.name} vor ...")
    stage()
    command = [
        sys.executable, "-m", "flet_cli.cli", "build", "apk", str(SRC),
        "-o", str(OUT),
        "--build-version", VERSION,
        "--build-number", str(build_number(VERSION)),
        "--yes",
    ]
    print(f"Baue die APK (Version {VERSION}) - beim ersten Mal lädt Flet die Android-Werkzeuge nach {TOOLS_DIR} ...")
    result = subprocess.call(command, cwd=ROOT, env=tool_env())
    if result != 0:
        return result
    apks = sorted(OUT.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    if not apks:
        print(f"FEHLER: Keine APK in {OUT} gefunden.")
        return 1
    DIST_APK.parent.mkdir(exist_ok=True)
    shutil.copy2(apks[-1], DIST_APK)
    print(f"Fertig: {DIST_APK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
