"""
ui/mail_dialogs.py
Dialoge für den Postfach-Abruf von Bestellbestätigungen (siehe
mail_fetch.py), wie in Version 1: Postfach-Einstellungen (IMAP-Zugang,
anbieterunabhängig, mit Verbindungstest) und die Auswahl der gefundenen
Bestellmails.
"""

from collections.abc import Callable

import flet as ft

import mail_fetch
import order_mail
from ui.common import TEXT_MUTED, close_dialog, run_background

_SECURITY_LABELS = {"ssl": "SSL/TLS (Port 993)", "starttls": "STARTTLS (Port 143)"}
_MANUAL = "Eigener Server / manuell"


def open_mail_settings_dialog(page: ft.Page) -> None:
    """IMAP-Zugang und Suchfilter. Das Passwort steht nie in config.json:
    wahlweise in den Windows-Anmeldeinformationen, sonst wird es bei jedem
    Abruf erfragt."""
    s = mail_fetch.load_settings()
    has_saved = mail_fetch.get_saved_password(s) is not None

    def number(label, value):
        return ft.TextField(label=label, value=str(value), dense=True, width=150,
                            input_filter=ft.NumbersOnlyInputFilter())

    preset = ft.Dropdown(label="Anbieter (Vorlage)", value=_MANUAL, dense=True,
                         options=[ft.DropdownOption(key=n, text=n) for n in (_MANUAL, *mail_fetch.PRESETS)])
    host = ft.TextField(label="IMAP-Server", value=s.host, hint_text="z. B. imap.gmx.net", dense=True)
    port = number("Port", s.port)
    security = ft.Dropdown(label="Verschlüsselung", value=s.security, dense=True, expand=True,
                           options=[ft.DropdownOption(key=k, text=v) for k, v in _SECURITY_LABELS.items()])
    user = ft.TextField(label="Benutzername", value=s.user, hint_text="meist die E-Mail-Adresse", dense=True)
    password = ft.TextField(label="Passwort", password=True, can_reveal_password=True, dense=True,
                            hint_text="gespeichert – leer lassen zum Beibehalten" if has_saved else "")
    save_pw = ft.Checkbox(label="Passwort in den Windows-Anmeldeinformationen speichern", value=has_saved,
                          disabled=not mail_fetch.keyring_available())
    folder = ft.TextField(label="Ordner", value=s.folder, dense=True)
    sender = ft.TextField(label="Absender enthält", value=s.sender, hint_text="leer = alle Absender", dense=True)
    subject = ft.TextField(label="Betreff enthält", value=s.subject, hint_text="leer = jeder Betreff", dense=True)
    days = number("Zeitraum (Tage zurück)", s.days_back)
    max_mails = number("Max. Mails je Abruf", s.max_messages)
    status = ft.Text("")
    test_btn = ft.TextButton("Verbindung testen")

    def apply_preset(_e):
        if preset.value in mail_fetch.PRESETS:
            h, p, sec = mail_fetch.PRESETS[preset.value]
            host.value, port.value, security.value = h, str(p), sec
            page.update()

    def sync_port(_e):
        if port.value in ("993", "143"):   # nur die Standard-Ports mitziehen
            port.value = "993" if security.value == "ssl" else "143"
            page.update()

    preset.on_select = apply_preset
    security.on_select = sync_port

    def current() -> mail_fetch.MailSettings:
        def as_int(field, default):
            try:
                return int(field.value)
            except (TypeError, ValueError):
                return default
        return mail_fetch.MailSettings(
            host=(host.value or "").strip(), port=as_int(port, 993), security=security.value or "ssl",
            user=(user.value or "").strip(), folder=(folder.value or "").strip() or "INBOX",
            sender=(sender.value or "").strip(), subject=(subject.value or "").strip(),
            days_back=as_int(days, 90), max_messages=as_int(max_mails, 30),
        )

    def test(_e):
        settings = current()
        pw = password.value or mail_fetch.get_saved_password(settings) or ""
        if not pw:
            status.value = "Bitte zum Testen ein Passwort eintragen."
            page.update()
            return
        test_btn.disabled = True
        status.value = "Teste Verbindung …"
        page.update()

        def done(count, error):
            test_btn.disabled = False
            status.value = f"❌ {error}" if error else \
                f"✔ Verbindung und Anmeldung erfolgreich ({count} Nachrichten im Ordner)."
            page.update()

        run_background(page, lambda: mail_fetch.test_connection(settings, pw), done)

    def delete_pw(_e):
        mail_fetch.delete_saved_password(current())
        save_pw.value = False
        password.hint_text = ""
        status.value = "Gespeichertes Passwort gelöscht."
        page.update()

    def save(_e):
        settings = current()
        mail_fetch.save_settings(settings)
        if s.credential_key != settings.credential_key and s.user:
            mail_fetch.delete_saved_password(s)   # Zugang geändert -> altes Passwort nicht verwaisen lassen
        if save_pw.value:
            if password.value and not mail_fetch.save_password(settings, password.value):
                status.value = "Das Passwort konnte nicht gespeichert werden - es wird beim Abruf erfragt."
                page.update()
                return
        else:
            mail_fetch.delete_saved_password(settings)
        close_dialog(page)

    test_btn.on_click = test
    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text("Postfach (IMAP) – Einstellungen"),
        content=ft.Container(ft.Column([
            preset, host, ft.Row([port, security]), user, password, save_pw,
            ft.Text("Das Passwort steht nie in der config.json. Bei GMX, WEB.DE, Gmail u. ä. ist oft ein "
                    "App-Passwort bzw. die Freigabe des IMAP-Zugriffs in den Kontoeinstellungen nötig.",
                    size=12, color=TEXT_MUTED),
            folder, sender, subject, ft.Row([days, max_mails]), status,
        ], tight=True, spacing=10, scroll=ft.ScrollMode.AUTO), width=560, height=620),
        actions=[test_btn, ft.TextButton("Gespeichertes Passwort löschen", on_click=delete_pw),
                 ft.FilledButton("Speichern", on_click=save),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))


def open_mail_select_dialog(page: ft.Page, mails: list, on_chosen: Callable[[list], None]) -> None:
    """Gefundene Bestellmails zur Auswahl; nur Mails mit auswertbarer
    Artikelliste, alle vorausgewählt."""
    usable = [m for m in mails if m.items]
    skipped = len(mails) - len(usable)
    boxes = []
    for mail in usable:
        when = mail.date.strftime("%d.%m.%Y") if mail.date else "ohne Datum"
        count = sum(i.menge for i in mail.items)
        kind = "abholbereit" if all(i.kind == order_mail.KIND_PICKUP for i in mail.items) else "Bestellung"
        boxes.append(ft.Checkbox(value=True,
                                 label=f"{when}  ·  {kind}  ·  {mail.subject or '(ohne Betreff)'}  ·  {count} Artikel"))

    def ok(_e):
        chosen = [m for m, box in zip(usable, boxes, strict=True) if box.value]
        close_dialog(page)
        if chosen:
            on_chosen(chosen)

    body = [ft.Text("Diese Bestellbestätigungen wurden gefunden – welche einlesen?"),
            ft.Container(ft.ListView(boxes, spacing=2), height=min(360, 40 * len(boxes) + 10))]
    if skipped:
        body.append(ft.Text(f"{skipped} weitere Mail(s) ohne auswertbare Artikelliste (z. B. Versandmitteilungen "
                            "oder nicht lesbare Mails) wurden übersprungen.", size=12, color=TEXT_MUTED))
    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text("Bestellungen aus dem Postfach"),
        content=ft.Container(ft.Column(body, tight=True, spacing=8), width=620),
        actions=[ft.FilledButton("Einlesen", on_click=ok),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))
