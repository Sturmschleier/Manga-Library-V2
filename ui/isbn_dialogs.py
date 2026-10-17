"""
ui/isbn_dialogs.py
ISBN-Abgleich / Bestellliste wie in Version 1: Auswahl (Monat/Jahr oder
VÖ +1 = TBA/NA, Buchhändler, vorhandene ISBNs erneut prüfen) und das
Ergebnisfenster mit Zusammenfassung und fertiger Bestellliste - Links sind
anklickbar, Zeilen mit Fallback-Link (keine ISBN gefunden) rosa, Zeilen mit
Sonderausgabe golden hinterlegt.
"""

import re
from collections.abc import Callable
from datetime import date

import flet as ft

import config
import shops
from ui.common import MONO, TEXT_MUTED, close_dialog, copy_text

# Markdown-Link [Text](URL) - bis zur Klammer, auf die Leerraum, Zeilenende
# oder eine Tabellen-Pipe folgt (URLs der buchhandel.de-Suche enthalten
# selbst Klammern) - oder eine nackte URL
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://\S+?)\)(?=\s|$|\|)|(https?://\S+)")
FALLBACK_BG = "#FBD3D3"
SONDERAUSGABE_BG = "#FFE08A"
LINK_COLOR = "#0B57D0"


def open_isbn_lookup_dialog(page: ft.Page, on_submit: Callable[[tuple], None]) -> None:
    """`on_submit` bekommt ("month", monat, jahr, overwrite) oder
    ("status", "TBA"/"NA", overwrite)."""
    today = date.today()
    shop = ft.Dropdown(label="Bestellen bei", value=shops.active_name(), dense=True, width=220,
                       options=[ft.DropdownOption(key=n, text=n) for n in shops.available()])
    month = ft.Dropdown(label="Monat", value=str(today.month), dense=True, width=110,
                        options=[ft.DropdownOption(key=str(m), text=str(m)) for m in range(1, 13)])
    year = ft.TextField(label="Jahr", value=str(today.year), dense=True, width=110,
                        input_filter=ft.NumbersOnlyInputFilter())
    overwrite = ft.Checkbox(label="Vorhandene ISBNs erneut prüfen (überschreiben)",
                            tooltip="Titel, für die es bereits einen ISBN-Cache-Eintrag für den aktuellen "
                                    "Band-Stand gibt, werden normalerweise übersprungen.")

    def changed(_e):
        month.disabled = year.disabled = group.value != "month"
        page.update()

    group = ft.RadioGroup(value="month", on_change=changed, content=ft.Column([
        ft.Radio(value="month", label="Nach Monat/Jahr (VÖ +1):"),
        ft.Row([ft.Container(width=24), month, year]),
        ft.Radio(value="TBA", label='Alle Titel mit VÖ +1 = "TBA"'),
        ft.Radio(value="NA", label='Alle Titel mit VÖ +1 = "NA"'),
    ], tight=True))

    def start(_e):
        shops.set_active(shop.value or shops.active_name())   # Auswahl dauerhaft merken
        if group.value == "month":
            try:
                y = int(year.value or "")
            except ValueError:
                year.error = "Jahr?"
                page.update()
                return
            selection = ("month", int(month.value), y, overwrite.value)
        else:
            selection = ("status", group.value, overwrite.value)
        close_dialog(page)
        on_submit(selection)

    page.show_dialog(ft.AlertDialog(
        modal=True, title=ft.Text("ISBN-Abgleich / Bestellliste"),
        content=ft.Container(ft.Column([
            ft.Text("Sucht für die ausgewählten Titel die ISBN des nächsten Bandes bei der DNB (eingeschränkt "
                    "auf das aktuelle Kalenderjahr und das Folgejahr) und erstellt eine Bestellliste mit Links."),
            ft.Row([shop, ft.Text("Fallback-Suche:"),
                    ft.Text(str(config.get("isbn_fallback_provider", "buchhandel.de")),
                            weight=ft.FontWeight.BOLD)], wrap=True),
            ft.Text("(änderbar über „Konfigurieren → Konfiguration …“)", size=12, color=TEXT_MUTED),
            group, overwrite,
        ], tight=True, spacing=8), width=580),
        actions=[ft.FilledButton("Suche starten", on_click=start),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))


def _line_control(line: str, fallback_marker: str, special_marker: str) -> ft.Control:
    spans = []
    pos = 0
    for m in _LINK_RE.finditer(line):
        start, end = m.span()
        if start > pos:
            spans.append(ft.TextSpan(line[pos:start]))
        label, url = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(3))
        spans.append(ft.TextSpan(label, url=url, style=ft.TextStyle(
            color=LINK_COLOR, decoration=ft.TextDecoration.UNDERLINE)))
        pos = end
    if pos < len(line):
        spans.append(ft.TextSpan(line[pos:]))
    bg = FALLBACK_BG if fallback_marker in line else SONDERAUSGABE_BG if special_marker in line else None
    return ft.Container(
        ft.Text(spans=spans or [ft.TextSpan(" ")], font_family=MONO, size=13, selectable=True),
        bgcolor=bg, padding=ft.Padding.symmetric(horizontal=4),
    )


def open_isbn_result(page: ft.Page, label: str, report, bestellliste_md: str) -> None:
    """Ergebnisfenster des ISBN-Abgleichs (IsbnResultWindow in Version 1)."""
    from isbn_lookup import SONDERAUSGABE_MARKER

    provider = config.get("isbn_fallback_provider", "buchhandel.de")
    fallback_marker = "manga-passion.de" if provider == "manga-passion" else "buchhandel.de"
    content = report.summary() if report else "(kein Ergebnis)"
    content += "\n\n" + ("─" * 70) + "\n\nBestellliste:\n\n" + (bestellliste_md or "")
    lines = ft.ListView([_line_control(line, fallback_marker, SONDERAUSGABE_MARKER) for line in content.split("\n")],
                        spacing=0, expand=True)
    copy_btn = ft.TextButton("Bestellliste in Zwischenablage kopieren")

    async def copy(_e):
        await copy_text(bestellliste_md or "")
        copy_btn.content = "✓ In Zwischenablage kopiert!"
        page.update()

    copy_btn.on_click = copy

    def legend(color, text):
        return ft.Row([ft.Container(width=14, height=14, bgcolor=color, border=ft.Border.all(1, "#888888")),
                       ft.Text(text, size=12)], spacing=6, tight=True)

    page.show_dialog(ft.AlertDialog(
        title=ft.Text(f"ISBN-Abgleich & Bestellliste – {label}"),
        content=ft.Container(ft.Column([
            ft.Row([legend(FALLBACK_BG, "= keine ISBN automatisch gefunden (manueller Fallback-Link)"),
                    legend(SONDERAUSGABE_BG, f"{SONDERAUSGABE_MARKER} = normale Ausgabe und Sonderausgabe vorhanden")],
                   wrap=True),
            ft.Container(lines, border=ft.Border.all(1, "#CCCCCC"), expand=True, bgcolor="#FFFFFF"),
        ], spacing=8), width=900, height=620),
        actions=[copy_btn, ft.FilledButton("Schließen", on_click=lambda _e: close_dialog(page))],
    ))
