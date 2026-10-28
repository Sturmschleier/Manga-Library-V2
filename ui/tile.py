"""
ui/tile.py
Eine Kachel der Kachelansicht - alle Kacheln sind gleich groß: Die
Textzeilen haben feste Höhen, das Cover wird ganz und unverzerrt in die
Fläche darüber eingepasst.

Inhalt: Cover von Band 1 (ohne Cover der Titel auf der Verlagsfarbe),
Titel, Verlag (Verlagsfarbe) und Typ, Komplett/Beendet (grün/rot wie in
Version 1), Besitz und Gelesen mit je einem "+1"-Knopf und dem Rückstand,
VÖ +1 mit seiner Statusfarbe (Beendet/TBA/Gestoppt/NA; neue, noch nicht
gespeicherte Termine rot). Der Rahmen zeigt den Status
(gallery.STATUS_BORDER_COLORS), Bestellt/Abholbereit stehen als Schild auf
dem Cover. Die Farben lassen sich wie in Version 1 unter "Konfigurieren →
Farben" abschalten (`colors_enabled`).

Die großen Kacheln (50 % breiter, siehe gallery.grid_columns) sind dieselbe
Kachel - nur der Platz im Raster ist größer, das Cover wächst mit. Für die
Listenansicht baut build_row eine Zeile mit kleinem Cover und denselben
Angaben nebeneinander (auf dem Handy zweizeilig, `compact`).

Bedienung: Klick wählt die Kachel aus, Doppelklick bearbeitet, Rechtsklick
öffnet das Kontextmenü - auf dem Handy langes Drücken (TileActions.long_press).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import flet as ft

import colors
import database as db
import gallery
import logic
from ui.theme import P

TILE_WIDTH = 220
COVER_RATIO = 0.72          # Breite : Höhe eines typischen Manga-Covers
DETAILS_HEIGHT = 198        # feste Höhe aller Zeilen unter dem Cover
TILE_ASPECT = TILE_WIDTH / (TILE_WIDTH / COVER_RATIO + DETAILS_HEIGHT)
ROW_HEIGHT = 84             # Listenansicht: Höhe einer Zeile (PC)
ROW_HEIGHT_COMPACT = 104    # Listenansicht auf dem Handy (zweizeilig)
THUMB_WIDTH = 52
BORDER_WIDTH = 4
RADIUS = 12
ON_PASTEL = colors.DEFAULT_TEXT_COLOR   # Schrift auf den hellen Verlags-/Statusfarben (beide Schemata)


@dataclass
class TileActions:
    """Was eine Kachel auslösen kann - jeweils mit der ID des Eintrags."""
    select: Callable
    edit: Callable
    plus_baende: Callable
    plus_gelesen: Callable
    context_items: Callable   # row_id -> [ft.PopupMenuItem] für das Rechtsklickmenü
    # Handy: row_id -> zeigt das Kontextmenü selbst an (statt Rechtsklick).
    # Flets ContextMenu reagiert auf Touch nicht zuverlässig.
    long_press: Optional[Callable] = None


def _enabled(colors_enabled: dict, key: str) -> bool:
    return (colors_enabled or {}).get(key, True)


def _chip(text: str, bgcolor: Optional[str], color: Optional[str] = None, tooltip: Optional[str] = None,
          bold: bool = False, expand=None) -> ft.Control:
    """Kleines Schild; ohne Farbe (None) das neutrale des Farbschemas."""
    if color is None:
        color = P.text if bgcolor is None else ON_PASTEL
    return ft.Container(
        ft.Text(text, size=11, color=color, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                weight=ft.FontWeight.BOLD if bold else None),
        bgcolor=bgcolor or P.chip, border_radius=6, padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        tooltip=tooltip, expand=expand,
    )


def _cover(entry: dict, status: str, image, colors_enabled: dict) -> ft.Control:
    if image:
        face = ft.Container(image=ft.DecorationImage(src=image, fit=ft.BoxFit.CONTAIN),
                            bgcolor=P.cover_bg, expand=True)
    else:
        face = ft.Container(
            ft.Text((entry.get("titel") or "(ohne Titel)").strip(), size=17, weight=ft.FontWeight.BOLD,
                    color=ON_PASTEL, text_align=ft.TextAlign.CENTER, max_lines=6,
                    overflow=ft.TextOverflow.ELLIPSIS),
            bgcolor=colors.verlag_color(entry.get("verlag") or "") or P.chip,
            alignment=ft.Alignment.CENTER, padding=12, expand=True,
        )
    layers = [ft.Container(face, expand=True, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                           border_radius=ft.BorderRadius.only(top_left=RADIUS - BORDER_WIDTH,
                                                              top_right=RADIUS - BORDER_WIDTH))]
    if status != gallery.STATUS_LAUFEND:
        layers.append(ft.Container(_chip(gallery.STATUS_LABELS[status], gallery.STATUS_BORDER_COLORS[status],
                                         "#FFFFFF", bold=True), right=6, top=6))
    order = _order_chip(entry, colors_enabled)
    if order is not None:
        layers.append(ft.Container(order, left=6, bottom=6))
    return ft.Stack(layers, expand=True)


def _order_chip(entry: dict, colors_enabled: dict) -> Optional[ft.Control]:
    """Schild "abholbereit" bzw. "bestellt" - oder None."""
    angekommen = (entry.get("angekommen") or "").strip()
    bestellt = (entry.get("bestellt") or "").strip()
    if angekommen and _enabled(colors_enabled, "angekommen"):
        return _chip(f"Band {angekommen} abholbereit", colors.ANGEKOMMEN_COLOR, bold=True)
    if bestellt and _enabled(colors_enabled, "bestellt"):
        return _chip(f"Band {bestellt} bestellt", colors.BESTELLT_COLOR, bold=True)
    return None


def _thumb(entry: dict, image, height: int) -> ft.Control:
    """Kleines Cover der Listenansicht; ohne Cover der Anfangsbuchstabe
    auf der Verlagsfarbe."""
    if image:
        return ft.Container(image=ft.DecorationImage(src=image, fit=ft.BoxFit.CONTAIN), bgcolor=P.cover_bg,
                            width=THUMB_WIDTH, height=height, border_radius=4)
    title = (entry.get("titel") or "?").strip() or "?"
    return ft.Container(
        ft.Text(title[0].upper(), size=22, weight=ft.FontWeight.BOLD, color=ON_PASTEL),
        bgcolor=colors.verlag_color(entry.get("verlag") or "") or P.chip,
        width=THUMB_WIDTH, height=height, border_radius=4, alignment=ft.Alignment.CENTER,
    )


def _counter(label: str, value: str, extra: str, tooltip: str, on_plus: Callable) -> ft.Control:
    return ft.Row(
        [
            ft.Text(label, size=13, color=P.text_muted, width=58),
            ft.Text(value or "–", size=15, weight=ft.FontWeight.BOLD, color=P.text),
            ft.Text(extra, size=11, color=P.text_muted, expand=True, max_lines=1),
            ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, icon_size=22, tooltip=tooltip, on_click=on_plus,
                          style=ft.ButtonStyle(padding=2), icon_color=P.accent),
        ],
        spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER, height=30,
    )


def _ja_nein_chip(label: str, value: str, enabled: bool) -> ft.Control:
    value = (value or "").strip()
    color = colors.ja_nein_color(value) if enabled else None
    return _chip(f"{label}: {value or '–'}", color, tooltip=f"{label}: {value or 'nicht angegeben'}")


def _voe_row(entry: dict, colors_enabled: dict) -> ft.Control:
    voe1 = (entry.get("voe_1") or "").strip()
    new_columns = logic.new_value_columns(entry)
    bg = colors.voe1_color(voe1) if _enabled(colors_enabled, "voe1") else None
    text_color = colors.NEW_VALUE_TEXT_COLOR if "voe_1" in new_columns else None
    tooltip_lines = [f"{db.LABELS[c]}: {(entry.get(c) or '').strip() or '–'}"
                     + ("  (neu, noch nicht gespeichert)" if c in new_columns else "") for c in db.VOE_COLUMNS]
    more = [c for c in db.VOE_COLUMNS[1:] if (entry.get(c) or "").strip()]
    return ft.Row(
        [
            ft.Icon(ft.Icons.EVENT, size=16, color=P.text_muted),
            _chip(voe1 or "–", bg, text_color, bold="voe_1" in new_columns, expand=True),
            ft.Text(f"+{len(more)}" if more else "", size=11,
                    color=colors.NEW_VALUE_TEXT_COLOR if set(more) & set(new_columns) else P.text_muted),
        ],
        spacing=4, height=24, tooltip="\n".join(tooltip_lines),
    )


def build_tile(entry: dict, image, actions: TileActions, colors_enabled: dict,
               selected: bool = False) -> ft.Control:
    """Baut die Kachel zu einem Eintrag; `image` ist das Cover (Dateipfad
    oder Bilddaten) oder None für den Platzhalter."""
    status = gallery.status_of(entry)
    row_id = entry.get("id")
    title = (entry.get("titel") or "(ohne Titel)").strip()
    verlag = (entry.get("verlag") or "").strip()
    typ = (entry.get("typ") or "").strip()
    rest = gallery.ruckstand(entry)
    verlag_bg = colors.verlag_color(verlag) if _enabled(colors_enabled, "verlag") else None

    details = ft.Column(
        [
            ft.Container(ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=P.text, max_lines=2,
                                 overflow=ft.TextOverflow.ELLIPSIS), height=38, tooltip=title),
            ft.Row([_chip(verlag or "–", verlag_bg, tooltip=f"Verlag: {verlag or '–'}"),
                    ft.Text(typ, size=12, color=P.text_muted, max_lines=1, expand=True)], spacing=6, height=22),
            ft.Row([_ja_nein_chip("Komplett", entry.get("komplett"), _enabled(colors_enabled, "komplett_beendet")),
                    _ja_nein_chip("Beendet", entry.get("beendet"), _enabled(colors_enabled, "komplett_beendet"))],
                   spacing=6, height=22),
            _counter("Besitz", entry.get("baende_bis") or "", "", "+1 Band gekauft",
                     lambda _e: actions.plus_baende(row_id)),
            _counter("Gelesen", entry.get("gelesen_bis") or "",
                     f"({rest} offen)" if rest else "", "+1 Band gelesen",
                     lambda _e: actions.plus_gelesen(row_id)),
            _voe_row(entry, colors_enabled),
        ],
        spacing=2,
    )

    card = ft.Container(
        content=ft.Column(
            [_cover(entry, status, image, colors_enabled),
             ft.Container(details, height=DETAILS_HEIGHT, padding=ft.Padding.only(left=10, right=4, bottom=6, top=4))],
            spacing=0,
        ),
        border=ft.Border.all(BORDER_WIDTH, gallery.STATUS_BORDER_COLORS[status]),
        border_radius=RADIUS,
        bgcolor=P.surface,
        shadow=ft.BoxShadow(spread_radius=3, blur_radius=6, color=P.accent) if selected else None,
    )
    return _interactive(card, row_id, actions)


def build_row(entry: dict, image, actions: TileActions, colors_enabled: dict,
              selected: bool = False, compact: bool = False) -> ft.Control:
    """Eine Zeile der Listenansicht: links ein Streifen in der Statusfarbe,
    kleines Cover, Titel mit Verlag und Typ, daneben Komplett/Beendet,
    Besitz und Gelesen mit "+1", VÖ +1 und die Schilder. `compact` (Handy):
    Zähler in einer zweiten Zeile, Komplett/Beendet und VÖ +1 entfallen."""
    status = gallery.status_of(entry)
    row_id = entry.get("id")
    title = (entry.get("titel") or "(ohne Titel)").strip()
    verlag = (entry.get("verlag") or "").strip()
    typ = (entry.get("typ") or "").strip()
    rest = gallery.ruckstand(entry)
    verlag_bg = colors.verlag_color(verlag) if _enabled(colors_enabled, "verlag") else None
    height = ROW_HEIGHT_COMPACT if compact else ROW_HEIGHT

    chips = [_chip(verlag or "–", verlag_bg, tooltip=f"Verlag: {verlag or '–'}")]
    if status != gallery.STATUS_LAUFEND:
        chips.append(_chip(gallery.STATUS_LABELS[status], gallery.STATUS_BORDER_COLORS[status], "#FFFFFF",
                           bold=True))
    order = _order_chip(entry, colors_enabled)
    if order is not None:
        chips.append(order)
    chips.append(ft.Text(typ, size=12, color=P.text_muted, max_lines=1, expand=True))
    heading = ft.Column(
        [ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=P.text, max_lines=1,
                 overflow=ft.TextOverflow.ELLIPSIS, tooltip=title),
         ft.Row(chips, spacing=6, height=22)],
        spacing=4, expand=True, alignment=ft.MainAxisAlignment.CENTER,
    )
    besitz = _counter("Besitz", entry.get("baende_bis") or "", "", "+1 Band gekauft",
                      lambda _e: actions.plus_baende(row_id))
    gelesen = _counter("Gelesen", entry.get("gelesen_bis") or "", f"({rest} offen)" if rest else "",
                       "+1 Band gelesen", lambda _e: actions.plus_gelesen(row_id))

    if compact:
        middle = ft.Column(
            [heading, ft.Row([ft.Container(besitz, expand=True), ft.Container(gelesen, expand=True)], spacing=4)],
            spacing=0, expand=True, alignment=ft.MainAxisAlignment.CENTER,
        )
        parts = [middle]
    else:
        ja_nein = _enabled(colors_enabled, "komplett_beendet")
        parts = [
            heading,
            ft.Column([_ja_nein_chip("Komplett", entry.get("komplett"), ja_nein),
                       _ja_nein_chip("Beendet", entry.get("beendet"), ja_nein)],
                      spacing=4, width=110, alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(besitz, width=150),
            ft.Container(gelesen, width=190),
            ft.Container(_voe_row(entry, colors_enabled), width=200),
        ]

    card = ft.Container(
        content=ft.Row(
            [ft.Container(width=6, bgcolor=gallery.STATUS_BORDER_COLORS[status]),
             ft.Container(_thumb(entry, image, height - 12), padding=ft.Padding.symmetric(vertical=6)),
             *parts],
            spacing=10, vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        height=height,
        padding=ft.Padding.only(right=8),
        border=ft.Border.all(2 if selected else 1, P.accent if selected else P.border),
        border_radius=8,
        bgcolor=P.surface,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )
    return _interactive(card, row_id, actions)


def _interactive(card: ft.Control, row_id, actions: TileActions) -> ft.Control:
    """Klick, Doppelklick und Kontextmenü (Rechtsklick bzw. langes Drücken)
    für eine Kachel oder Listenzeile."""
    if actions.long_press is not None:
        return ft.Container(
            ft.GestureDetector(
                content=card,
                on_tap=lambda _e: actions.select(row_id),
                on_double_tap=lambda _e: actions.edit(row_id),
                on_long_press_start=lambda _e: actions.long_press(row_id),
            ),
            key=ft.ScrollKey(f"t{row_id}"),
            data=row_id,
        )
    return ft.ContextMenu(
        content=ft.GestureDetector(
            content=card,
            on_tap=lambda _e: actions.select(row_id),
            on_double_tap=lambda _e: actions.edit(row_id),
            mouse_cursor=ft.MouseCursor.CLICK,
        ),
        secondary_items=actions.context_items(row_id),
        key=ft.ScrollKey(f"t{row_id}"),
        data=row_id,
    )
