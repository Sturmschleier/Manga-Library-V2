"""
ui/calendar_dialog.py
Monatlicher Veröffentlichungskalender: eine Zeile je Erscheinungstag mit
den Verlagen dahinter, darunter die Titel mit Bandnummer. Termine ohne
festen Tag (nur MM.JJJJ) stehen am Ende. Grundlage sind allein die
VÖ-Einträge (VÖ +1 bis VÖ +3) des Zwischenspeichers, also auch noch nicht
gespeicherte Änderungen. Die Logik steckt in release_calendar.py.

Ein Klick auf einen Titel öffnet dessen Bearbeiten-Dialog.
"""

from datetime import date
from typing import Optional

import flet as ft

import colors
import release_calendar as rc
from ui.common import TEXT_MUTED, close_dialog, copy_text

TODAY_BG = "#E3EEFF"
DAY_BG = "#F3F5F8"
NEUTRAL_CHIP = "#E9ECF1"


def _chip(text: str, bgcolor: str, color: str = colors.DEFAULT_TEXT_COLOR, bold: bool = False) -> ft.Control:
    return ft.Container(
        ft.Text(text, size=12, color=color, weight=ft.FontWeight.BOLD if bold else None),
        bgcolor=bgcolor, border_radius=6, padding=ft.Padding.symmetric(horizontal=6, vertical=1),
    )


class CalendarDialog:
    def __init__(self, app, year: Optional[int] = None, month: Optional[int] = None):
        self.app = app
        self.page = app.page
        today = date.today()
        self.year, self.month = year or today.year, month or today.month

        self.title = ft.Text(size=20, weight=ft.FontWeight.BOLD, width=230, text_align=ft.TextAlign.CENTER)
        self.summary = ft.Text(size=13, color=TEXT_MUTED)
        self.list = ft.ListView(spacing=4, expand=True)
        self.copy_btn = ft.TextButton("Als Text kopieren", icon=ft.Icons.CONTENT_COPY, on_click=self._copy)
        header = ft.Row(
            [
                ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Vorheriger Monat", on_click=lambda _e: self._go(-1)),
                self.title,
                ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Nächster Monat", on_click=lambda _e: self._go(1)),
                ft.TextButton("Heute", on_click=lambda _e: self._today()),
            ],
            spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        width = min((self.page.width or 1400) - 80, 920)
        height = max(360, (self.page.height or 900) - 160)
        self.dialog = ft.AlertDialog(
            title=ft.Text("Veröffentlichungskalender"),
            content=ft.Container(ft.Column([header, self.summary, ft.Divider(height=1), self.list], spacing=8),
                                 width=width, height=height),
            actions=[self.copy_btn, ft.FilledButton("Schließen", on_click=lambda _e: close_dialog(self.page))],
        )
        self._fill()
        self.page.show_dialog(self.dialog)

    # ------------------------------------------------------------ Aufbau

    def _view(self) -> rc.MonthView:
        return rc.month_view(self.app.buffer.data, self.year, self.month)

    def _fill(self):
        view = self._view()
        self.title.value = rc.month_title(self.year, self.month)
        undated = f" · {len(view.undated)} ohne festen Tag" if view.undated else ""
        self.summary.value = (f"{view.count} Bände an {len(view.days)} Erscheinungstagen{undated}"
                              + (f" · {len(view.verlage)} Verlage" if view.verlage else ""))
        rows = []
        today = date.today()
        for day, releases in view.days:
            rows.append(self._day_header(rc.day_label(day), releases, day == today, day < today))
            rows += [self._release_row(r) for r in releases]
        if view.undated:
            rows.append(self._day_header("Ohne festen Tag", view.undated, False, False))
            rows += [self._release_row(r) for r in view.undated]
        if not rows:
            rows.append(ft.Container(ft.Text("In diesem Monat sind keine Termine eingetragen.", color=TEXT_MUTED),
                                     padding=20))
        self.list.controls = rows

    def _day_header(self, label: str, releases, is_today: bool, is_past: bool) -> ft.Control:
        verlage = rc.verlage_of(releases)
        chips = [_chip(v, colors.verlag_color(v) or NEUTRAL_CHIP) for v in verlage]
        return ft.Container(
            ft.Row(
                [ft.Text(label, weight=ft.FontWeight.BOLD, size=14, width=130,
                         color=TEXT_MUTED if is_past else colors.DEFAULT_TEXT_COLOR),
                 ft.Text("–", color=TEXT_MUTED),
                 ft.Row(chips, spacing=4, wrap=True, expand=True),
                 ft.Text(f"{len(releases)} Bd.", size=12, color=TEXT_MUTED)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=TODAY_BG if is_today else DAY_BG, border_radius=6,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6), margin=ft.Margin.only(top=6),
        )

    def _release_row(self, r: rc.Release) -> ft.Control:
        image = self.app._image_for(r.titel)
        thumb = (ft.Image(src=image, width=26, height=38, fit=ft.BoxFit.CONTAIN, border_radius=2) if image
                 else ft.Container(width=26, height=38, border_radius=2,
                                   bgcolor=colors.verlag_color(r.verlag) or NEUTRAL_CHIP))
        badges = []
        if r.abholbereit:
            badges.append(_chip("abholbereit", colors.ANGEKOMMEN_COLOR, bold=True))
        elif r.bestellt:
            badges.append(_chip("bestellt", colors.BESTELLT_COLOR, bold=True))
        if r.neu:
            badges.append(_chip("neu, noch nicht gespeichert", NEUTRAL_CHIP, colors.NEW_VALUE_TEXT_COLOR))
        title_color = colors.NEW_VALUE_TEXT_COLOR if r.neu else colors.DEFAULT_TEXT_COLOR
        return ft.Container(
            ft.Row(
                [thumb,
                 ft.Text(rc.release_label(r), size=14, color=title_color, expand=True, max_lines=2,
                         overflow=ft.TextOverflow.ELLIPSIS),
                 *badges,
                 ft.Text(r.verlag, size=12, color=TEXT_MUTED, width=150, max_lines=1,
                         overflow=ft.TextOverflow.ELLIPSIS),
                 ft.Text(r.typ, size=12, color=TEXT_MUTED, width=80)],
                spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=30, right=10, top=2, bottom=2), border_radius=6,
            on_click=lambda _e, entry_id=r.entry_id: self._edit(entry_id), ink=True,
            tooltip="Klicken zum Bearbeiten",
        )

    # ----------------------------------------------------------- Aktionen

    def _go(self, delta: int):
        self.year, self.month = rc.shift_month(self.year, self.month, delta)
        self._fill()
        self.page.update()

    def _today(self):
        today = date.today()
        self.year, self.month = today.year, today.month
        self._fill()
        self.page.update()

    def _edit(self, entry_id):
        close_dialog(self.page)
        self.app.edit_entry(entry_id)

    async def _copy(self, _e):
        await copy_text(rc.as_text(self._view()))
        self.copy_btn.content = "✓ Kopiert"
        self.page.update()
