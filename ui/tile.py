"""
ui/tile.py
Eine Kachel der Kachelansicht: Cover-Fläche, Titel, Verlag/Typ, Besitz und
Gelesen mit je einem "+1"-Knopf, nächster Termin. Der Rahmen zeigt den
Status (Beendet/TBA/NA/Gestoppt, siehe gallery.STATUS_BORDER_COLORS).

Solange es noch keine Cover gibt, steht auf der Cover-Fläche der Titel auf
der Verlagsfarbe (colors.verlag_color) - dieselbe Fläche nimmt später das
Bild des ersten Bandes auf.
"""

from collections.abc import Callable

import flet as ft

import colors
import gallery

TILE_WIDTH = 210
BORDER_WIDTH = 4
RADIUS = 12
TEXT_DARK = colors.DEFAULT_TEXT_COLOR
TEXT_MUTED = "#5F6673"


def _cover(entry: dict, status: str) -> ft.Control:
    title = (entry.get("titel") or "(ohne Titel)").strip()
    face = ft.Container(
        content=ft.Text(
            title, size=17, weight=ft.FontWeight.BOLD, color=TEXT_DARK,
            text_align=ft.TextAlign.CENTER, max_lines=5, overflow=ft.TextOverflow.ELLIPSIS,
        ),
        bgcolor=colors.verlag_color(entry.get("verlag") or "") or "#E3E6EB",
        alignment=ft.Alignment.CENTER,
        padding=12,
        border_radius=ft.BorderRadius.only(top_left=RADIUS - BORDER_WIDTH, top_right=RADIUS - BORDER_WIDTH),
        expand=True,
    )
    badges = []
    if status != gallery.STATUS_LAUFEND:
        badges.append(ft.Container(
            content=ft.Text(gallery.STATUS_LABELS[status], size=11, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
            bgcolor=gallery.STATUS_BORDER_COLORS[status],
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=8,
            right=6, top=6,
        ))
    angekommen = (entry.get("angekommen") or "").strip()
    bestellt = (entry.get("bestellt") or "").strip()
    if angekommen or bestellt:
        text, color = (f"Band {angekommen} abholbereit", colors.ANGEKOMMEN_COLOR) if angekommen \
            else (f"Band {bestellt} bestellt", colors.BESTELLT_COLOR)
        badges.append(ft.Container(
            content=ft.Text(text, size=11, weight=ft.FontWeight.W_600, color=TEXT_DARK),
            bgcolor=color,
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=8,
            left=6, bottom=6,
        ))
    return ft.Stack([face, *badges], expand=True)


def _counter(label: str, value: str, tooltip: str, on_plus: Callable) -> ft.Control:
    return ft.Row(
        [
            ft.Text(label, size=13, color=TEXT_MUTED, width=62),
            ft.Text(value or "–", size=15, weight=ft.FontWeight.BOLD, color=TEXT_DARK, expand=True),
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE, icon_size=22, tooltip=tooltip, on_click=on_plus,
                style=ft.ButtonStyle(padding=2), icon_color="#3B5BA9",
            ),
        ],
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        height=34,
    )


def build_tile(entry: dict, on_plus_baende: Callable, on_plus_gelesen: Callable) -> ft.Control:
    """Baut die Kachel zu einem Eintrag. Die Callbacks bekommen die ID des
    Eintrags."""
    status = gallery.status_of(entry)
    row_id = entry.get("id")
    title = (entry.get("titel") or "(ohne Titel)").strip()
    sub = " · ".join(v for v in ((entry.get("verlag") or "").strip(), (entry.get("typ") or "").strip()) if v)
    release = gallery.next_release(entry)

    details = ft.Column(
        [
            ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=TEXT_DARK, max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS, tooltip=title),
            ft.Text(sub or " ", size=12, color=TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            _counter("Besitz", entry.get("baende_bis") or "", "+1 Band gekauft",
                     lambda _e: on_plus_baende(row_id)),
            _counter("Gelesen", entry.get("gelesen_bis") or "", "+1 Band gelesen",
                     lambda _e: on_plus_gelesen(row_id)),
            ft.Row(
                [
                    ft.Icon(ft.Icons.EVENT, size=16, color=TEXT_MUTED),
                    ft.Text(release or "–", size=12, color=TEXT_DARK if release else TEXT_MUTED,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                ],
                spacing=4,
                tooltip="Nächster Termin (VÖ +1)",
            ),
        ],
        spacing=2,
    )

    return ft.Container(
        content=ft.Column(
            [_cover(entry, status), ft.Container(details, padding=ft.Padding.only(left=10, right=4, bottom=8))],
            spacing=6,
        ),
        border=ft.Border.all(BORDER_WIDTH, gallery.STATUS_BORDER_COLORS[status]),
        border_radius=RADIUS,
        bgcolor="#FFFFFF",
        data=row_id,
    )
