"""
appinfo.py
Version und Programminformationen für den Dialog "Über …" - ohne
Oberfläche, damit sie sich testen lassen.

Neue Version veröffentlichen: VERSION anheben, mergen und das GitHub-Release
mit dem Tag "v<VERSION>" anlegen (siehe ENTWICKLUNG.md, Kapitel "Neue Version
veröffentlichen").
"""

import platform
import sqlite3
import sys
from dataclasses import dataclass
from importlib import metadata
from typing import Optional

VERSION = "2.0.0"
REPOSITORY_URL = "https://github.com/Sturmschleier/Manga-Library-V2"

# Verwendete Bibliotheken: (Anzeigename, Paketnamen für die Versionsabfrage,
# wofür das Programm sie braucht, Lizenz). Die Paketnamen nutzt auch
# MangaLibrary.spec, um die Versionsangaben mit in die exe zu packen.
LIBRARIES = (
    ("Flet", ("flet",), "Programmoberfläche (auf Basis von Flutter)", "Apache-2.0"),
    ("requests", ("requests",), "ISBN-Abgleich (Abfragen bei der DNB)", "Apache-2.0"),
    ("google-api-python-client", ("google-api-python-client",), "Sicherung in Google Drive", "Apache-2.0"),
    ("google-auth", ("google-auth",), "Anmeldung bei Google", "Apache-2.0"),
    ("google-auth-oauthlib", ("google-auth-oauthlib",), "Google-Anmeldung im Browser", "Apache-2.0"),
    ("google-auth-httplib2", ("google-auth-httplib2",), "Verbindung zu Google", "Apache-2.0"),
    ("keyring", ("keyring",), "Postfach-Passwort in den Windows-Anmeldeinformationen", "MIT"),
)


@dataclass
class Component:
    name: str
    version: Optional[str]   # None = nicht installiert (die Funktion steht dann nicht zur Verfügung)
    zweck: str
    lizenz: str


def _package_version(names) -> Optional[str]:
    """Version des ersten installierten Pakets aus `names` (ohne es zu
    importieren), sonst None."""
    for name in names:
        for candidate in (name, name.replace("_", "-"), name.replace("-", "_")):
            try:
                return metadata.version(candidate)
            except metadata.PackageNotFoundError:
                continue
    return None


def components() -> list[Component]:
    """Laufzeit und verwendete Bibliotheken mit ihren Versionen."""
    result = [
        Component("Python", f"{platform.python_version()} ({platform.architecture()[0]})",
                  "Programmiersprache und Laufzeit", "PSF-2.0"),
    ]
    result.append(Component("SQLite", sqlite3.sqlite_version, "Datenbank der Sammlung", "Public Domain"))
    for name, packages, zweck, lizenz in LIBRARIES:
        result.append(Component(name, _package_version(packages), zweck, lizenz))
    return result


def about_text(data_dir: Optional[str] = None) -> str:
    """Programminformationen als Text - z.B. zum Kopieren für eine Fehlermeldung."""
    frozen = " (exe)" if getattr(sys, "frozen", False) else ""
    lines = [f"Manga Library V2 {VERSION}{frozen}", REPOSITORY_URL]
    if data_dir:
        lines.append(f"Datenordner: {data_dir}")
    lines.append(f"Betriebssystem: {platform.platform()}")
    lines.append("")
    lines.append("Verwendete Module:")
    for c in components():
        lines.append(f"  {c.name}: {c.version or 'nicht installiert'} – {c.zweck} ({c.lizenz})")
    return "\n".join(lines)
