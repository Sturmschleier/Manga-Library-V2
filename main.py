"""
main.py
Einstiegspunkt: startet die Manga & Light Novel Bibliothek, Version 2 (Flet).

Aufruf:
    python main.py
"""

import os
import sys
import threading
import time
import traceback

import flet as ft

import changelog
import database as db
from instance_lock import InstanceLock
from ui import APP_TITLE

_lock = InstanceLock(str(db.DB_FILE) + ".lock")

# So lange darf Flet nach dem Schließen des Fensters noch aufräumen
EXIT_GRACE_SECONDS = 3


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


def _exit_soon():
    """Nach dem endgültigen Schließen des Fensters: Beendet das Programm
    spätestens nach EXIT_GRACE_SECONDS. Flet (1.0.4) wartet sonst
    gelegentlich endlos auf das bereits geschlossene Fenster, und das
    Programm bliebe unsichtbar im Task-Manager hängen - samt Sperre gegen
    ein zweites Programmfenster. Zu diesem Zeitpunkt ist alles gespeichert
    oder bewusst verworfen; endet ft.run() rechtzeitig von selbst, kommt
    dieser Thread (daemon) gar nicht mehr zum Zug."""

    def run():
        time.sleep(EXIT_GRACE_SECONDS)
        _lock.release()
        os._exit(0)

    threading.Thread(target=run, name="exit-soon", daemon=True).start()


def _main(page: ft.Page):
    from ui.app import MangaApp

    MangaApp(page, on_closed=_exit_soon)


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
