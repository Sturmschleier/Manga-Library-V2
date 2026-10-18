"""
ui/isbn_dialogs.py
ISBN-Abgleich / Bestellliste wie in Version 1: Auswahl (Monat/Jahr oder
VÖ +1 = TBA/NA, Buchhändler, vorhandene ISBNs erneut prüfen) und das
Ergebnisfenster mit Zusammenfassung und fertiger Bestellliste - Links sind
anklickbar, Zeilen mit Fallback-Link (keine ISBN gefunden) rosa, Zeilen mit
Sonderausgabe golden hinterlegt. Bereits bestellte Bände bekommen am
Zeilenanfang einen hellblauen Balken (Farbe wie die Markierung "bestellt").
"""

import re
from collections.abc import Callable
from datetime import date

import flet as ft

import colors
import config
import shops
from ui.common import MONO, close_dialog, copy_text
from ui.theme import P

# Markdown-Link [Text](URL) - bis zur Klammer, auf die Leerraum, Zeilenende
# oder eine Tabellen-Pipe folgt (URLs der buchhandel.de-Suche enthalten
# selbst Klammern) - oder eine nackte URL
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://\S+?)\)(?=\s|$|\|)|(https?://\S+)")
FALLBACK_BG = "#FBD3D3"
SONDERAUSGABE_BG = "#FFE08A"
CHAR_WIDTH = 7.6     # Breite eines Zeichens der Festbreitenschrift (Consolas, Größe 13)
LINE_HEIGHT = 19
ORDERED_BAR_WIDTH = 6   # hellblauer Balken vor bereits bestellten Bänden


class SpinBox:
    """Zahlenfeld mit Pfeilen nach oben/unten (wie QSpinBox in Version 1):
    eintippen oder mit den Pfeilen um 1 ändern, begrenzt auf min..max."""

    def __init__(self, page: ft.Page, label: str, value: int, minimum: int, maximum: int, width: int):
        self.page, self.minimum, self.maximum = page, minimum, maximum
        self.field = ft.TextField(label=label, value=str(value), dense=True, width=width,
                                  input_filter=ft.NumbersOnlyInputFilter(), on_blur=lambda _e: self._clamp())
        self.up = self._arrow(ft.Icons.ARROW_DROP_UP, 1, f"{label} +1")
        self.down = self._arrow(ft.Icons.ARROW_DROP_DOWN, -1, f"{label} −1")
        self.control = ft.Row([self.field, ft.Column([self.up, self.down], spacing=0, tight=True)],
                              spacing=2, tight=True)

    def _arrow(self, icon, step: int, tooltip: str) -> ft.Control:
        return ft.Container(ft.Icon(icon, size=22), width=26, height=20, ink=True, border_radius=4,
                            tooltip=tooltip, on_click=lambda _e: self._step(step))

    def _number(self):
        try:
            return int(self.field.value or "")
        except ValueError:
            return None

    def _set(self, value: int) -> None:
        self.field.value = str(min(self.maximum, max(self.minimum, value)))
        self.field.error = None
        self.page.update()

    def _step(self, step: int) -> None:
        if self.field.disabled:
            return
        current = self._number()
        self._set(self.minimum if current is None else current + step)

    def _clamp(self) -> None:
        current = self._number()
        if current is not None:
            self._set(current)

    @property
    def disabled(self) -> bool:
        return bool(self.field.disabled)

    @disabled.setter
    def disabled(self, value: bool) -> None:
        self.field.disabled = self.up.disabled = self.down.disabled = value
        self.up.opacity = self.down.opacity = 0.35 if value else 1.0

    def read(self):
        """Der Wert (auf min..max begrenzt) oder None, wenn das Feld keine
        Zahl enthält - dann zeigt das Feld einen Hinweis."""
        current = self._number()
        if current is None:
            self.field.error = f"{self.field.label}?"
            return None
        return min(self.maximum, max(self.minimum, current))


def open_isbn_lookup_dialog(page: ft.Page, on_submit: Callable[[tuple], None]) -> None:
    """`on_submit` bekommt ("month", monat, jahr, overwrite) oder
    ("status", "TBA"/"NA", overwrite)."""
    today = date.today()
    shop = ft.Dropdown(label="Bestellen bei", value=shops.active_name(), dense=True, width=220,
                       options=[ft.DropdownOption(key=n, text=n) for n in shops.available()])
    month = SpinBox(page, "Monat", today.month, 1, 12, width=90)
    year = SpinBox(page, "Jahr", today.year, 1900, 2100, width=110)
    overwrite = ft.Checkbox(label="Vorhandene ISBNs erneut prüfen (überschreiben)",
                            tooltip="Titel, für die es bereits einen ISBN-Cache-Eintrag für den aktuellen "
                                    "Band-Stand gibt, werden normalerweise übersprungen.")

    def changed(_e):
        month.disabled = year.disabled = group.value != "month"
        page.update()

    group = ft.RadioGroup(value="month", on_change=changed, content=ft.Column([
        ft.Radio(value="month", label="Nach Monat/Jahr (VÖ +1):"),
        ft.Row([ft.Container(width=24), month.control, year.control]),
        ft.Radio(value="TBA", label='Alle Titel mit VÖ +1 = "TBA"'),
        ft.Radio(value="NA", label='Alle Titel mit VÖ +1 = "NA"'),
    ], tight=True))

    def start(_e):
        shops.set_active(shop.value or shops.active_name())   # Auswahl dauerhaft merken
        if group.value == "month":
            m, y = month.read(), year.read()
            if m is None or y is None:
                page.update()
                return
            selection = ("month", m, y, overwrite.value)
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
            ft.Text("(änderbar über „Konfigurieren → Konfiguration …“)", size=12, color=P.text_muted),
            group, overwrite,
        ], tight=True, spacing=8), width=580),
        actions=[ft.FilledButton("Suche starten", on_click=start),
                 ft.TextButton("Abbrechen", on_click=lambda _e: close_dialog(page))],
    ))


def _visible_length(line: str) -> int:
    """Länge der Zeile, wie sie angezeigt wird (Links nur mit ihrem Text)."""
    return len(_LINK_RE.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(3), line))


def _plain_spans(text: str, ordered_marker: str) -> list:
    """Text ohne Links; die Bestellt-Markierung bekommt den hellblauen Hintergrund."""
    spans = []
    for i, part in enumerate(text.split(ordered_marker)):
        if i:
            spans.append(ft.TextSpan(ordered_marker, style=ft.TextStyle(
                bgcolor=colors.BESTELLT_COLOR, color="#1A1A1A", weight=ft.FontWeight.BOLD)))
        if part:
            spans.append(ft.TextSpan(part))
    return spans


def _line_control(line: str, fallback_marker: str, special_marker: str, ordered_marker: str,
                  no_wrap: bool = False) -> ft.Control:
    spans = []
    pos = 0
    for m in _LINK_RE.finditer(line):
        start, end = m.span()
        if start > pos:
            spans.extend(_plain_spans(line[pos:start], ordered_marker))
        label, url = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(3))
        spans.append(ft.TextSpan(label, url=url, style=ft.TextStyle(
            decoration=ft.TextDecoration.UNDERLINE)))
        pos = end
    if pos < len(line):
        spans.extend(_plain_spans(line[pos:], ordered_marker))
    bg = FALLBACK_BG if fallback_marker in line else SONDERAUSGABE_BG if special_marker in line else None
    # auf den hellen Markierungen dunkle Schrift und Links, sonst die des Farbschemas
    text_color, link_color = ("#1A1A1A", "#0B57D0") if bg else (P.text, P.link)
    for span in spans:
        if span.url:
            span.style.color = link_color
    # Balken am Zeilenanfang als linker Rand; ohne Markierung durchsichtig und
    # gleich breit, damit die Spalten der Festbreitenschrift bündig bleiben
    bar_color = colors.BESTELLT_COLOR if ordered_marker in line else ft.Colors.TRANSPARENT
    return ft.Container(
        ft.Text(spans=spans or [ft.TextSpan(" ")], font_family=MONO, size=13, selectable=True, no_wrap=no_wrap,
                color=text_color),
        bgcolor=bg, padding=ft.Padding.symmetric(horizontal=4),
        border=ft.Border.only(left=ft.BorderSide(ORDERED_BAR_WIDTH, bar_color)),
    )


def open_isbn_result(page: ft.Page, label: str, report, bestellliste_md: str) -> None:
    """Ergebnisfenster des ISBN-Abgleichs (IsbnResultWindow in Version 1)."""
    from isbn_lookup import BESTELLT_MARKER, SONDERAUSGABE_MARKER

    provider = config.get("isbn_fallback_provider", "buchhandel.de")
    fallback_marker = "manga-passion.de" if provider == "manga-passion" else "buchhandel.de"
    content = report.summary() if report else "(kein Ergebnis)"
    content += "\n\n" + ("─" * 70) + "\n\nBestellliste:\n\n" + (bestellliste_md or "")
    raw_lines = content.split("\n")
    # So breit, dass keine Zeile umbricht - höchstens so breit wie das
    # Programmfenster; was dann noch zu lang ist, bricht um
    longest = max((_visible_length(line) for line in raw_lines), default=40)
    available = (page.width or 1400) - 80
    width = min(available, max(700, longest * CHAR_WIDTH + 70 + ORDERED_BAR_WIDTH))
    no_wrap = longest * CHAR_WIDTH + 70 + ORDERED_BAR_WIDTH <= available
    height = min((page.height or 900) - 220, max(240, LINE_HEIGHT * len(raw_lines) + 70))
    lines = ft.ListView([_line_control(line, fallback_marker, SONDERAUSGABE_MARKER, BESTELLT_MARKER, no_wrap)
                         for line in raw_lines], spacing=0, expand=True)
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
                    legend(SONDERAUSGABE_BG, f"{SONDERAUSGABE_MARKER} = normale Ausgabe und Sonderausgabe vorhanden"),
                    legend(colors.BESTELLT_COLOR, f"{BESTELLT_MARKER} = Band ist bereits bestellt")],
                   wrap=True),
            ft.Container(lines, border=ft.Border.all(1, P.border), expand=True, bgcolor=P.surface),
        ], spacing=8), width=width, height=height),
        actions=[copy_btn, ft.FilledButton("Schließen", on_click=lambda _e: close_dialog(page))],
    ))
