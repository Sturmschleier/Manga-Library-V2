"""
build_exe.py
Baut MangaLibraryV2.exe mit "flet pack" - wird von build.bat in der
Build-Umgebung .venv-build aufgerufen (die festen Versionen stehen in
requirements-build.txt).

"flet pack" ruft PyInstaller auf und packt zusätzlich den Flet-Desktop-
Client (das eigentliche Programmfenster, ca. 100 MB) in die exe. Ohne ihn
lüde die exe den Client beim ersten Start aus dem Internet nach. Beim
ersten Start entpackt die exe den Client einmalig nach
%USERPROFILE%\\.flet\\client.

Hier steht, was zusätzlich in die exe kommt (früher MangaLibrary.spec):
- Von den über 500 Google-API-Beschreibungen (ca. 100 MB) nur die für
  Google Drive v3 (drive_sync.py: build("drive", "v3")).
- Die Paket-Metadaten der Bibliotheken aus appinfo.LIBRARIES, damit der
  Über-Dialog auch in der exe die Versionen anzeigen kann.
"""

import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import googleapiclient

from appinfo import LIBRARIES, VERSION

ROOT = Path(__file__).resolve().parent
EXE_NAME = "MangaLibraryV2"


def _metadata_args() -> list:
    args = []
    for _name, packages, _zweck, _lizenz in LIBRARIES:
        for package in packages:
            try:
                distribution(package)
            except PackageNotFoundError:
                continue
            args.append(f"--copy-metadata={package}")
            break
    return args


def main() -> int:
    drive_json = Path(googleapiclient.__file__).parent / "discovery_cache" / "documents" / "drive.v3.json"
    if not drive_json.is_file():
        print(f"FEHLER: {drive_json} fehlt - ist google-api-python-client installiert?")
        return 1

    command = [
        sys.executable, "-m", "flet_cli.cli", "pack", "main.py",
        "--yes",
        "--name", EXE_NAME,
        "--product-name", "Manga Library V2",
        "--file-description", "Manga Library V2",
        "--product-version", VERSION,
        "--file-version", f"{VERSION}.0",
        "--company-name", "Sturmschleier",
        "--copyright", "© 2026 Sturmschleier, MIT-Lizenz",
        "--add-data", f"{drive_json};googleapiclient/discovery_cache/documents",
        "--hidden-import",
        "google_auth_httplib2",       # einzelnes Modul, wird von googleapiclient nur bei Bedarf geladen
        "keyring.backends.Windows",   # Windows-Anmeldeinformationen für das IMAP-Passwort (mail_fetch.py)
        # ab hier Argumente für PyInstaller selbst
        "--",
        "--clean",
        "--collect-all=google_auth_oauthlib",
        "--exclude-module=tkinter",
        *_metadata_args(),
    ]
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
