"""
ui/dialogs.py
In sich geschlossene Dialoge wie in Version 1 (gui/dialogs.py):
Eintrag anlegen/bearbeiten, Konfiguration (config.json direkt bearbeiten),
Über …, Auswahl für den Abgleich der VÖ-Termine - dazu neu "Cover neu
suchen". Sie schreiben nie selbst in den Zwischenspeicher, sondern geben die
Eingaben an einen Callback weiter.
"""

import json
from collections.abc import Callable
from typing import Optional

import flet as ft

import appinfo
import config
import database as db
import logic
from ui.common import MONO, TEXT_MUTED, close_dialog, copy_text, open_path, open_url

TYP_OPTIONEN = ["Manga", "Manhwa", "Light Novel"]
JA_NEIN_OPTIONEN = ["Ja", "Nein"]


def _combo(label: str, value: str, options: list) -> ft.Dropdown:
    """Auswahlfeld, in das man auch frei schreiben kann (editierbare
    QComboBox in Version 1)."""
    return ft.Dropdown(
        label=label, value=value or None, text=value or "", editable=True, enable_filter=True, dense=True,
        options=[ft.DropdownOption(key=o, text=o) for o in options], expand=True, menu_height=300,
    )


def _combo_value(field: ft.Dropdown) -> str:
    return (field.text if field.text is not None else field.value or "").strip()


def open_entry_dialog(page: ft.Page, title: str, on_save: Callable[[dict], None], initial: Optional[dict] = None,
                      verlag_values=(), other_titles=()) -> None:
    """Formular für alle Spalten eines Werks. Vor dem Übernehmen wird geprüft
    (logic.validate_entry, u. a. doppelte Titel); `other_titles` sind die
    klein geschriebenen Titel aller ANDEREN Einträge."""
    initial = initial or {}
    fields = {}
    for col in db.COLUMN_NAMES:
        value = initial.get(col) or ""
        if col == "typ":
            field = _combo(db.LABELS[col], value, TYP_OPTIONEN)
        elif col in ("komplett", "beendet"):
            field = _combo(db.LABELS[col], value, JA_NEIN_OPTIONEN)
        elif col == "verlag":
            field = _combo(db.LABELS[col], value, list(verlag_values))
        else:
            field = ft.TextField(label=db.LABELS[col], value=value, dense=True, expand=True,
                                 multiline=col == "kommentar", max_lines=3 if col == "kommentar" else 1)
        fields[col] = field
    error = ft.Text("", color="#B00020")

    def value_of(col):
        field = fields[col]
        return _combo_value(field) if isinstance(field, ft.Dropdown) else (field.value or "").strip()

    def save(_e=None):
        values = {col: value_of(col) for col in db.COLUMN_NAMES}
        problems = logic.validate_entry(values, other_titles)
        if problems:
            error.value = "\n".join(problems)
            page.update()
            return
        close_dialog(page)
        on_save(values)

    def row(*cols):
        return ft.Row([fields[c] for c in cols], spacing=10)

    form = ft.Column(
        [
            row("titel"),
            row("baende_bis", "gelesen_bis"),
            row("komplett", "beendet"),
            row("typ", "zugang"),
            row("verlag"),
            row("voe_1", "voe_2", "voe_3"),
            row("kommentar"),
            ft.Text("Datumswerte als TT.MM.JJJJ oder MM.JJJJ; Freitext wie „TBA“ oder „Fortlaufend“ ist erlaubt.",
                    size=12, color=TEXT_MUTED),
            error,
        ],
        spacing=12, tight=True,
    )
    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text(title), content=ft.Container(form, width=620),
        actions=[ft.FilledButton("Übernehmen", on_click=save),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))


def open_config_dialog(page: ft.Page, on_saved: Callable) -> None:
    """Direkter Editor für config.json: prüft JSON-Syntax sowie Typen und
    Werte der bekannten Einstellungen (config.validate), bevor gespeichert wird."""
    editor = ft.TextField(
        value=json.dumps(config.load(), indent=2, ensure_ascii=False, sort_keys=True),
        multiline=True, min_lines=16, max_lines=16, text_style=ft.TextStyle(font_family=MONO, size=13),
    )
    error = ft.Text("", color="#B00020")

    def save(_e):
        try:
            parsed = json.loads(editor.value or "")
        except json.JSONDecodeError as exc:
            error.value = f"Ungültiges JSON: {exc}"
            page.update()
            return
        if not isinstance(parsed, dict):
            error.value = "Der Inhalt muss ein JSON-Objekt sein (z.B. { \"schlüssel\": \"wert\" })."
            page.update()
            return
        problems = config.validate(parsed)
        if problems:
            error.value = "Nicht gespeichert:\n" + "\n".join(problems)
            page.update()
            return
        config.save(parsed)
        close_dialog(page)
        on_saved()

    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text("Konfiguration bearbeiten"),
        content=ft.Container(ft.Column([
            ft.Text(f"Datei: {config.CONFIG_FILE}", size=12, selectable=True),
            ft.Text("z.B. „isbn_shop_name“/„isbn_shop_url_template“ (Standard-Buchhändler für gefundene ISBNs, "
                    "{isbn} wird durch die jeweilige ISBN ersetzt), „isbn_fallback_provider“ (\"buchhandel.de\" "
                    "oder \"manga-passion\"), „follow_selection_after_edit“, „sidebar_width_fraction“, "
                    "„cover_auto_lookup“.", size=12, color=TEXT_MUTED),
            editor, error,
        ], tight=True, spacing=8), width=640),
        actions=[ft.FilledButton("Speichern", on_click=save),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))


def open_about_dialog(page: ft.Page, data_dir) -> None:
    """Version, Links zum Quellcode und zum Datenordner, verwendete Module."""
    text = appinfo.about_text(str(data_dir))
    copy_btn = ft.TextButton("In Zwischenablage kopieren")

    async def copy(_e):
        await copy_text(text)
        copy_btn.content = "✓ Kopiert"
        page.update()

    copy_btn.on_click = copy
    rows = [
        ft.DataRow(cells=[ft.DataCell(ft.Text(v, size=12)) for v in
                          (c.name, c.version or "nicht installiert", c.zweck, c.lizenz)])
        for c in appinfo.components()
    ]
    table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text(h, weight=ft.FontWeight.BOLD)) for h in
                 ("Modul", "Version", "Verwendet für", "Lizenz")],
        rows=rows, data_row_min_height=26, data_row_max_height=34, heading_row_height=32, column_spacing=16,
    )
    page.show_dialog(ft.AlertDialog(
        title=ft.Text("Über Manga Library V2"),
        content=ft.Container(ft.Column([
            ft.Text(f"Version {appinfo.VERSION}", weight=ft.FontWeight.BOLD),
            ft.Text("Verwaltet deine Manga-, Manhwa- und Light-Novel-Sammlung."),
            ft.Row([ft.Text("Quellcode und Versionen:"),
                    ft.TextButton(appinfo.REPOSITORY_URL, on_click=lambda _e: open_url(appinfo.REPOSITORY_URL))],
                   wrap=True),
            ft.Row([ft.Text("Datenordner (Datenbank, covers, LOG, BACKUP):"),
                    ft.TextButton(str(data_dir), on_click=lambda _e: open_path(data_dir))], wrap=True),
            ft.Text("Verwendete Module", weight=ft.FontWeight.BOLD),
            table,
        ], tight=True, spacing=6), width=780),
        actions=[copy_btn, ft.FilledButton("Schließen", on_click=lambda _e: close_dialog(page))],
    ))


def open_cover_refresh_dialog(page: ft.Page, counts: dict, on_start: Callable[[bool], None]) -> None:
    """Auswahl für "Cover neu suchen": nur fehlende oder alle (eigene Bilder
    bleiben immer). `counts` = {"fehlend": n, "alle": n}."""
    group = ft.RadioGroup(value="fehlend", content=ft.Column([
        ft.Radio(value="fehlend", label=f"Nur Titel ohne Cover  ({counts['fehlend']})"),
        ft.Radio(value="alle", label=f"Alle Titel neu suchen  ({counts['alle']})"),
    ], tight=True))

    def start(_e):
        close_dialog(page)
        on_start(group.value == "fehlend")

    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text("Cover neu suchen"),
        content=ft.Container(ft.Column([
            ft.Text("Sucht das Cover von Band 1 erneut: zuerst bei der Deutschen Nationalbibliothek, "
                    "als Ausweichlösung im VLB (buchhandel.de). Läuft im Hintergrund - die Bibliothek "
                    "bleibt bedienbar."),
            group,
            ft.Text("Selbst gewählte Bilder bleiben immer erhalten.", size=12, color=TEXT_MUTED),
        ], tight=True, spacing=10), width=520),
        actions=[ft.FilledButton("Suche starten", on_click=start),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))


VLB_OPTIONS = (
    ("alle", "Alle Serien"),
    ("datum", "Nur mit Datum in VÖ +1"),
    ("tba", "Nur mit VÖ +1 = TBA"),
    ("na", "Nur mit VÖ +1 = NA"),
)


def open_vlb_dialog(page: ft.Page, counts: dict, pause: float, on_start: Callable[[str], None]) -> None:
    """Auswahl für den Abgleich mit buchhandel.de mit Anzahl und geschätzter
    Dauer je Auswahl (wie VlbLookupDialog in Version 1)."""
    first = next((s for s, _l in VLB_OPTIONS if counts.get(s, 0)), "alle")
    estimate = ft.Text()
    start_btn = ft.FilledButton("Abfrage starten")

    def update_estimate(_e=None):
        count = counts.get(group.value, 0)
        minutes = max(1, round(count * pause / 60)) if count else 0
        estimate.value = f"{count} Serien, Dauer etwa {minutes} Minute(n)." if count \
            else "Keine Serie zur Abfrage vorhanden."
        start_btn.disabled = not count
        page.update()

    group = ft.RadioGroup(value=first, on_change=update_estimate, content=ft.Column([
        ft.Radio(value=scope, label=f"{label}  ({counts.get(scope, 0)})", disabled=not counts.get(scope, 0))
        for scope, label in VLB_OPTIONS
    ], tight=True))

    def start(_e):
        close_dialog(page)
        on_start(group.value)

    start_btn.on_click = start
    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text("VÖ-Termine von buchhandel.de"),
        content=ft.Container(ft.Column([
            ft.Text("Fragt bei buchhandel.de die Termine neuer Bände ab - eine Serie nach der anderen, mit "
                    "Pausen dazwischen. Neue Termine erscheinen rot in VÖ +1 bis VÖ +3 und gelten erst nach "
                    "„Speichern“ (vorher mit „Rückgängig“ zurücknehmbar)."),
            group,
            ft.Text("Übersprungen werden: Komplett = Ja sowie VÖ +1 = Fortlaufend, Gestoppt oder Beendet.",
                    size=12, color=TEXT_MUTED),
            estimate,
        ], tight=True, spacing=10), width=560),
        actions=[start_btn, ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))
    update_estimate()
