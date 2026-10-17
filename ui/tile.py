"""
ui/tile.py
Eine Kachel der Kachelansicht: Cover von Band 1, Titel, Verlag/Typ, Besitz
und Gelesen mit je einem "+1"-Knopf, nächster Termin. Der Rahmen zeigt den
Status (Beendet/TBA/NA/Gestoppt, siehe gallery.STATUS_BORDER_COLORS).

Ohne Cover (noch nicht gesucht, nicht gefunden oder entfernt) steht auf der
Cover-Fläche der Titel auf der Verlagsfarbe (colors.verlag_color). Das
Menü oben links auf dem Cover sucht erneut, nimmt ein eigenes Bild oder
entfernt das Cover.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import flet as ft

import colors
import gallery

TILE_WIDTH = 210
BORDER_WIDTH = 4
RADIUS = 12
TEXT_DARK = colors.DEFAULT_TEXT_COLOR
TEXT_MUTED = "#5F6673"


@dataclass
class TileActions:
    """Was die Knöpfe einer Kachel auslösen - jeweils mit der ID des Eintrags."""
    plus_baende: Callable
    plus_gelesen: Callable
    cover_search: Callable
    cover_pick: Callable
    cover_remove: Callable


def _placeholder(entry: dict) -> ft.Control:
    title = (entry.get("titel") or "(ohne Titel)").strip()
    return ft.Container(
        content=ft.Text(
            title, size=17, weight=ft.FontWeight.BOLD, color=TEXT_DARK,
            text_align=ft.TextAlign.CENTER, max_lines=5, overflow=ft.TextOverflow.ELLIPSIS,
        ),
        bgcolor=colors.verlag_color(entry.get("verlag") or "") or "#E3E6EB",
        alignment=ft.Alignment.CENTER,
        padding=12,
        expand=True,
    )


def _badge(text: str, bgcolor: str, color: str = TEXT_DARK, **position) -> ft.Control:
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, color=color),
        bgcolor=bgcolor,
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        border_radius=8,
        **position,
    )


def _cover_menu(row_id, has_cover: bool, actions: TileActions) -> ft.Control:
    items = [
        ft.PopupMenuItem(content="Cover erneut suchen", icon=ft.Icons.IMAGE_SEARCH,
                         on_click=lambda _e: actions.cover_search(row_id)),
        ft.PopupMenuItem(content="Eigenes Bild wählen …", icon=ft.Icons.FOLDER_OPEN,
                         on_click=lambda _e: actions.cover_pick(row_id)),
    ]
    if has_cover:
        items.append(ft.PopupMenuItem(content="Cover entfernen", icon=ft.Icons.HIDE_IMAGE,
                                      on_click=lambda _e: actions.cover_remove(row_id)))
    return ft.Container(
        content=ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, icon_size=18, items=items, tooltip="Cover"),
        bgcolor="#D9FFFFFF",   # Weiß, leicht durchsichtig (Flutter: #AARRGGBB)
        border_radius=16,
        width=32, height=32,
        left=4, top=4,
    )


def _cover(entry: dict, status: str, image: Optional[bytes], actions: TileActions) -> ft.Control:
    if image:
        # als Hintergrundbild, damit es die ganze Fläche füllt (ft.Image
        # behält seine eigene Breite)
        face = ft.Container(image=ft.DecorationImage(src=image, fit=ft.BoxFit.COVER), expand=True,
                            bgcolor="#E3E6EB")
    else:
        face = _placeholder(entry)
    layers = [ft.Container(face, expand=True, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                           border_radius=ft.BorderRadius.only(top_left=RADIUS - BORDER_WIDTH,
                                                              top_right=RADIUS - BORDER_WIDTH))]
    if status != gallery.STATUS_LAUFEND:
        layers.append(_badge(gallery.STATUS_LABELS[status], gallery.STATUS_BORDER_COLORS[status],
                             "#FFFFFF", right=6, top=6))
    angekommen = (entry.get("angekommen") or "").strip()
    bestellt = (entry.get("bestellt") or "").strip()
    if angekommen:
        layers.append(_badge(f"Band {angekommen} abholbereit", colors.ANGEKOMMEN_COLOR, left=6, bottom=6))
    elif bestellt:
        layers.append(_badge(f"Band {bestellt} bestellt", colors.BESTELLT_COLOR, left=6, bottom=6))
    layers.append(_cover_menu(entry.get("id"), bool(image), actions))
    return ft.Stack(layers, expand=True)


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


def build_tile(entry: dict, image: Optional[bytes], actions: TileActions) -> ft.Control:
    """Baut die Kachel zu einem Eintrag; `image` ist das Cover (Bilddaten)
    oder None für den Platzhalter."""
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
                     lambda _e: actions.plus_baende(row_id)),
            _counter("Gelesen", entry.get("gelesen_bis") or "", "+1 Band gelesen",
                     lambda _e: actions.plus_gelesen(row_id)),
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
            [_cover(entry, status, image, actions),
             ft.Container(details, padding=ft.Padding.only(left=10, right=4, bottom=8))],
            spacing=6,
        ),
        border=ft.Border.all(BORDER_WIDTH, gallery.STATUS_BORDER_COLORS[status]),
        border_radius=RADIUS,
        bgcolor="#FFFFFF",
        data=row_id,
    )
