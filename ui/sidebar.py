"""
ui/sidebar.py
Die Seitenleiste rechts - wie in Version 1, von oben nach unten:
Suche, Statistik (Summe im Besitz, Summe gelesen, Differenz, Gelesen-
Anteil), Anzahl nach Verlag, Anzahl nach Typ (Gesamt / Gelesen / Offen),
Erscheinungstermine (aktueller, nächster, übernächster Monat und
ausstehende Termine - ein Klick auf einen Monat öffnet ihn im
Veröffentlichungskalender) und das Live-Log dieser Sitzung.

Die Zahlen rechnet gallery.py (ohne Oberfläche, getestet).
"""

from datetime import date
from typing import Optional

import flet as ft

import gallery
from ui.common import TEXT_MUTED, section, value_row

ALT_ROW = "#F3F5F8"   # abwechselnde Zeilenfarbe wie setAlternatingRowColors


class Sidebar:
    def __init__(self, search_field: ft.TextField, on_open_month=None):
        """`on_open_month(offset)` öffnet den Kalender: 0 = aktueller Monat,
        1 = nächster, 2 = übernächster."""
        self.search_field = search_field

        stats = [value_row(label) for label in
                 ("Summe im Besitz:", "Summe gelesen:", "Differenz (Besitz − gelesen):", "Gelesen-Anteil:")]
        self.besitz, self.gelesen, self.differenz, self.anteil = (value for _row, value in stats)

        # feste Höhen: die Seitenleiste scrollt als Ganzes, wenn das Fenster
        # niedrig ist - sonst würden Verlagsliste und Live-Log zerquetscht
        self.verlag_list = ft.ListView(spacing=0, height=170)
        self.typ_list = ft.Column(spacing=0, tight=True)

        releases = [value_row(label) for label in ("Aktueller Monat:", "Nächster Monat:", "Übernächster Monat:")]
        self.release_values = [value for _row, value in releases]
        overdue_row, self.overdue = value_row("Vor aktuellem Monat:")

        self.log_view = ft.ListView(spacing=2, height=200, auto_scroll=True)
        self.log_placeholder = ft.Text("Änderungen erscheinen hier, sobald sie passieren …",
                                       size=12, italic=True, color=TEXT_MUTED)
        self.log_view.controls.append(self.log_placeholder)

        def clickable(row, offset):
            if on_open_month is None:
                return row
            return ft.Container(row, on_click=lambda _e: on_open_month(offset), ink=True, border_radius=4,
                                tooltip="Im Veröffentlichungskalender öffnen")

        releases_box = section("Erscheinungstermine", [
            *[clickable(row, offset) for offset, (row, _v) in enumerate(releases)],
            ft.Divider(height=8),
            ft.Text("Ausstehende Termine", weight=ft.FontWeight.BOLD, size=13),
            overdue_row,
        ])
        releases_box.tooltip = (
            "Zählt Termine (Treffer über alle drei VÖ-Spalten VÖ +1 … VÖ +3), nicht eindeutige Titel - "
            "ein Titel mit zwei Terminen im selben Zeitraum zählt also zweimal.\n"
            "„Ausstehende Termine“ = vermutlich bereits erschienen, aber „Bände (bis)“ noch nicht "
            "per „+1“ nachgetragen."
        )
        typ_box = section("Anzahl nach Typ", [
            ft.Text("Gesamt / Gelesen / Offen", size=12, italic=True, color=TEXT_MUTED),
            self.typ_list,
        ])
        typ_box.tooltip = ("Gesamt = Summe „Bände (bis)“, Gelesen = Summe „Gelesen bis“, "
                           "Offen = Gesamt − Gelesen, jeweils je Typ (in dieser Reihenfolge).")

        self.control = ft.Column(
            [
                ft.Row([ft.Text("Suche:", size=13), search_field], spacing=6),
                section("Statistik", [row for row, _v in stats]),
                section("Anzahl nach Verlag", [self.verlag_list]),
                typ_box,
                releases_box,
                section("Live-Log (diese Sitzung)", [self.log_view]),
            ],
            spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, scroll=ft.ScrollMode.AUTO,
        )

    @staticmethod
    def _list_row(text: str, index: int) -> ft.Control:
        return ft.Container(ft.Text(text, size=13), bgcolor=ALT_ROW if index % 2 else None,
                            padding=ft.Padding.symmetric(horizontal=4, vertical=2))

    def update(self, entries, exclude_gestoppt: bool, today: Optional[date] = None) -> None:
        """Alle Zahlen neu berechnen. Summen und Typ-Bilanz respektieren
        "Gestoppt: keine Berechnung", die Verlagsliste nicht (wie Version 1)."""
        stats_entries = gallery.stats_entries(entries, exclude_gestoppt)
        totals = gallery.totals(stats_entries)
        self.besitz.value = str(totals["besitz"])
        self.gelesen.value = str(totals["gelesen"])
        self.differenz.value = str(totals["differenz"])
        self.anteil.value = f"{totals['anteil']:.1f} %"

        self.verlag_list.controls = [
            self._list_row(f"{verlag}  ({count})", i) for i, (verlag, count) in
            enumerate(gallery.counts_by(entries, "verlag"))
        ]
        self.typ_list.controls = [
            self._list_row(f"{typ}: {gesamt} · {gelesen} · {offen}", i) for i, (typ, gesamt, gelesen, offen) in
            enumerate(gallery.typ_balance(stats_entries))
        ]

        counts, overdue = gallery.release_counts(entries, today)
        for value, count in zip(self.release_values, counts, strict=True):
            value.value = str(count)
        self.overdue.value = str(overdue)

    def log(self, line: str) -> None:
        if self.log_placeholder in self.log_view.controls:
            self.log_view.controls.remove(self.log_placeholder)
        self.log_view.controls.append(ft.Text(line, size=12, selectable=True))
