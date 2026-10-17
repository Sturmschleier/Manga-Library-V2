"""
main.py
Einstiegspunkt: startet die Manga & Light Novel Bibliothek, Version 2 (Flet).

Aufruf:
    python main.py
"""

import sys
import traceback

import flet as ft

import changelog
import database as db
from instance_lock import InstanceLock
from ui import APP_TITLE

_lock = InstanceLock(str(db.DB_FILE) + ".lock")


def _install_excepthook():
    """Schreibt unerwartete Fehler nach LOG/fehler.log - in der exe (ohne
    Konsole) gingen sie sonst unbemerkt verloren."""

    def hook(exc_type, exc_value, exc_tb):
        try:
            changelog.log_error("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        except Exception:  # noqa: BLE001 - der Fehler-Handler selbst darf nicht abstürzen
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


def _already_running(page: ft.Page):
    page.title = APP_TITLE
    page.add(ft.Text(
        "Die Bibliothek ist bereits in einem anderen Programmfenster geöffnet.\n\n"
        "Bitte das bereits geöffnete Fenster verwenden – ein zweites würde beim Speichern "
        "die Änderungen des ersten überschreiben.",
        size=16,
    ))


def _main(page: ft.Page):
    from ui.app import MangaApp

    MangaApp(page)


def main():
    _install_excepthook()
    if not _lock.acquire():
        ft.run(_already_running)
        sys.exit(1)
    try:
        ft.run(_main)
    finally:
        _lock.release()


if __name__ == "__main__":
    main()
