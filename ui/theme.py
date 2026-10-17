"""
ui/theme.py
Farbschema der Oberfläche: hell, dunkel oder wie Windows ("system"),
einstellbar unter "Konfigurieren → Darstellung" (config: theme_mode).

Alle eigenen Flächen- und Schriftfarben stehen hier in je einer Palette;
die Oberfläche liest sie beim Aufbauen aus `P` (z.B. P.surface). Ein
Wechsel des Schemas baut das Fenster neu auf (ui.app.MangaApp.set_theme).
Die hellen Pastellfarben für Verlag und Status (colors.py) bleiben in beiden
Schemata gleich und behalten ihre dunkle Schrift.
"""

from dataclasses import dataclass, fields

import flet as ft

import config

THEME_OPTIONS = (("system", "Wie Windows (System)"), ("light", "Hell"), ("dark", "Dunkel"))


@dataclass
class Palette:
    page_bg: str
    surface: str        # Kacheln, Kästen der Seitenleiste, Menüleiste
    text: str
    text_muted: str
    border: str
    chip: str           # neutrales Schild (ohne Farbbedeutung)
    alt_row: str        # abwechselnde Zeilen
    cover_bg: str       # Fläche hinter einem eingepassten Cover
    today_bg: str
    day_bg: str
    link: str
    accent: str         # Auswahlrahmen, "+1"-Knöpfe


LIGHT = Palette(
    page_bg="#F2F4F7", surface="#FFFFFF", text="#1A1A1A", text_muted="#5F6673", border="#D5D9E0",
    chip="#E9ECF1", alt_row="#F3F5F8", cover_bg="#EEF0F3", today_bg="#E3EEFF", day_bg="#F3F5F8",
    link="#0B57D0", accent="#3B5BA9",
)
DARK = Palette(
    page_bg="#15171B", surface="#22252B", text="#E6E8EB", text_muted="#9AA3AF", border="#3A3F48",
    chip="#353A42", alt_row="#2A2E35", cover_bg="#1B1E23", today_bg="#23395B", day_bg="#2A2E35",
    link="#8AB4F8", accent="#8EA8FF",
)

# Die aktuell gültige Palette - wird von apply() umgestellt
P = Palette(**{f.name: getattr(LIGHT, f.name) for f in fields(Palette)})


def mode() -> str:
    value = str(config.get("theme_mode", "system") or "system")
    return value if value in dict(THEME_OPTIONS) else "system"


def is_dark(page: ft.Page) -> bool:
    current = mode()
    if current == "system":
        return page.platform_brightness == ft.Brightness.DARK
    return current == "dark"


def apply(page: ft.Page) -> bool:
    """Stellt Palette und Flet-Schema passend zur Einstellung ein; gibt
    zurück, ob jetzt das dunkle Schema gilt."""
    dark = is_dark(page)
    source = DARK if dark else LIGHT
    for f in fields(Palette):
        setattr(P, f.name, getattr(source, f.name))
    page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
    page.bgcolor = P.page_bg
    return dark
