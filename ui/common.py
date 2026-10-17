"""
ui/common.py
Gemeinsame Bausteine der Oberfläche: Meldungen, Rückfragen, Fortschritts-
fenster für Hintergrund-Aufgaben, Passwort-Abfrage, Browser/Ordner öffnen,
Zwischenablage. Entspricht QMessageBox, QProgressDialog, QInputDialog und
gui/worker.AsyncCall aus Version 1.
"""

import os
import threading
import webbrowser
from collections.abc import Callable
from typing import Optional

import flet as ft

TEXT_MUTED = "#5F6673"
MONO = "Consolas"


def close_dialog(page: ft.Page) -> None:
    try:
        page.pop_dialog()
    except Exception:  # noqa: BLE001 - kein Dialog offen: nichts zu tun
        pass


def _details(details: str) -> ft.Control:
    return ft.ExpansionTile(
        title=ft.Text("Details", size=13),
        controls=[ft.Container(
            ft.Text(details, selectable=True, size=12, font_family=MONO),
            height=min(320, 18 * (details.count("\n") + 2)), padding=8,
        )],
    )


def alert(page: ft.Page, title: str, text: str, details: str = "", on_close: Optional[Callable] = None) -> None:
    """Meldung mit OK - optional mit aufklappbaren Details (wie
    QMessageBox.setDetailedText)."""
    def ok(_e):
        close_dialog(page)
        if on_close:
            on_close()

    body = [ft.Text(text, selectable=True)]
    if details:
        body.append(_details(details))
    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text(title),
        content=ft.Container(ft.Column(body, tight=True, scroll=ft.ScrollMode.AUTO), width=560),
        actions=[ft.FilledButton("OK", on_click=ok)],
    ))


def ask(page: ft.Page, title: str, text: str, buttons: list) -> None:
    """Rückfrage mit eigenen Knöpfen: [(Beschriftung, Callback oder None,
    hervorgehoben)]. Jeder Knopf schließt den Dialog und ruft dann seinen
    Callback (None = nur schließen)."""
    def make(callback):
        def click(_e):
            close_dialog(page)
            if callback:
                callback()
        return click

    actions = [
        (ft.FilledButton if primary else ft.TextButton)(label, on_click=make(callback))
        for label, callback, primary in buttons
    ]
    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text(title), content=ft.Container(ft.Text(text), width=520), actions=actions,
    ))


def confirm(page: ft.Page, title: str, text: str, on_yes: Callable, yes: str = "Ja", no: str = "Nein") -> None:
    """Ja/Nein-Frage; "Nein" ist wie in Version 1 die vorsichtige Wahl."""
    ask(page, title, text, [(yes, on_yes, False), (no, None, True)])


def prompt_password(page: ft.Page, title: str, text: str, on_ok: Callable[[str], None]) -> None:
    field = ft.TextField(password=True, can_reveal_password=True, autofocus=True)

    def ok(_e=None):
        value = field.value or ""
        close_dialog(page)
        if value:
            on_ok(value)

    field.on_submit = ok
    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text(title),
        content=ft.Column([ft.Text(text), field], tight=True, width=420),
        actions=[ft.FilledButton("OK", on_click=ok),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))


class Busy:
    """Fortschrittsfenster für eine Hintergrund-Aufgabe (wie QProgressDialog):
    unbestimmter Balken, bis `progress()` Zahlen meldet. Mit `cancellable`
    gibt es "Abbrechen": Das setzt `cancel_event` und lässt das Fenster
    offen, bis die Aufgabe den gerade laufenden Schritt beendet hat."""

    def __init__(self, page: ft.Page, title: str, text: str, cancellable: bool = False,
                 cancel_text: str = "Wird abgebrochen …"):
        self.page = page
        self.cancel_event = threading.Event()
        self._cancel_text = cancel_text
        self.text = ft.Text(text)
        self.bar = ft.ProgressBar(value=None, width=440)
        self.cancel_btn = ft.TextButton("Abbrechen", on_click=self._cancel, visible=cancellable)
        self.dialog = ft.AlertDialog(
            modal=True, title=ft.Text(title),
            content=ft.Column([self.text, self.bar], tight=True, width=460),
            actions=[self.cancel_btn],
        )
        page.show_dialog(self.dialog)

    def _cancel(self, _e):
        self.cancel_event.set()
        self.text.value = self._cancel_text
        self.cancel_btn.visible = False
        self.page.update()

    def progress(self, done: int, total: int, text: str) -> None:
        """Aus dem Hintergrund-Thread aufrufbar."""
        if self.cancel_event.is_set():
            return   # Hinweis "wird abgebrochen" stehen lassen
        self.bar.value = (done / total) if total else None
        self.text.value = text
        self.page.update()

    def close(self) -> None:
        if self.dialog.open:
            close_dialog(self.page)


def run_background(page: ft.Page, func: Callable, on_done: Callable) -> None:
    """Führt `func()` in einem eigenen Thread aus und ruft danach
    `on_done(result, error)` auf (error = Exception oder None) - wie
    gui/worker.AsyncCall in Version 1."""
    def worker():
        result, error = None, None
        try:
            result = func()
        except Exception as exc:  # noqa: BLE001 - wird dem Nutzer angezeigt
            error = exc
        on_done(result, error)

    page.run_thread(worker)


def open_url(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except webbrowser.Error:
        return False


def open_path(path) -> None:
    """Ordner oder Datei mit dem zugehörigen Windows-Programm öffnen."""
    os.startfile(str(path))


async def copy_text(text: str) -> None:
    await ft.Clipboard().set(text)


def section(title: str, controls: list, expand=None) -> ft.Control:
    """Umrandeter Kasten der Seitenleiste (wie QFrame StyledPanel)."""
    return ft.Container(
        ft.Column([ft.Text(title, weight=ft.FontWeight.BOLD, size=13), *controls], spacing=4,
                  tight=expand is None, expand=expand is not None),
        border=ft.Border.all(1, "#D5D9E0"), border_radius=8, padding=10, bgcolor="#FFFFFF", expand=expand,
    )


def value_row(label: str) -> tuple:
    """Zeile "Bezeichnung ... Wert" - gibt (Zeile, Wert-Text) zurück."""
    value = ft.Text("0", weight=ft.FontWeight.BOLD, size=13)
    row = ft.Row([ft.Text(label, size=13, expand=True), value], spacing=6)
    return row, value
