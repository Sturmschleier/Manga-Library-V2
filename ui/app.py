"""
ui/app.py
Das Hauptfenster - aufgebaut wie Version 1, nur mit Kacheln statt Tabelle:

- Menüleiste "Datei", "Konfigurieren", "Hilfe" mit allen Einträgen aus
  Version 1 (dazu "Cover neu suchen …")
- Werkzeugleiste: Rückgängig, Wiederholen, Speichern, Google Drive, ISBN-
  Abgleich, VÖ-Termine, VÖ-Kalender, Filter (Verlag, VÖ +1, Bestellung,
  Typ), Sortierung
- Veröffentlichungskalender je Monat (ui/calendar_dialog.py)
- Kachelansicht (Klick wählt aus, Doppelklick bearbeitet, Rechtsklick öffnet
  das Kontextmenü)
- Seitenleiste rechts (ui/sidebar.py): Suche, Statistik, Verlage, Typen,
  Erscheinungstermine, Live-Log
- Statuszeile mit Anzahl, ungespeicherten Änderungen, Cover-Suche und
  Farblegende

Wie in Version 1 wirken alle Änderungen zuerst nur auf den Zwischenspeicher
(library.LibraryBuffer, mit Rückgängig/Wiederholen); erst "Speichern"
schreibt in die Datenbank, vorher wird sie nach BACKUP/ gesichert.

Die Aktionen stehen thematisch getrennt in Mixins: ui/actions_data.py (CSV,
Bestellungen, Google Drive), ui/actions_lookup.py (ISBN, VÖ-Termine,
buchhandel.de), ui/actions_covers.py (Cover). Der Geräte-Abgleich im WLAN
hat ein eigenes Fenster (ui/sync_dialog.py).

Auf dem Handy (Android-App, siehe build_apk.py) ist der Aufbau kompakter:
eine Zeile mit Symbolknöpfen und einem Menü statt Menü- und
Werkzeugleiste, die Filter in einer wischbaren Zeile, die Seitenleiste als
„Übersicht“ zum Hochschieben, langes Drücken statt Rechtsklick. Weil Android
eine App im Hintergrund jederzeit beenden kann, wird dort beim Wechsel in
den Hintergrund automatisch gespeichert.
"""

import inspect
import threading
from datetime import date

import flet as ft

import changelog
import colors
import config
import database as db
import gallery
import logic
import release_calendar
from library import LibraryBuffer
from ui import APP_TITLE, theme
from ui.actions_covers import CoverActions
from ui.actions_data import DataActions
from ui.actions_lookup import LookupActions
from ui.common import alert, ask, can_open_paths, close_dialog, confirm, is_mobile, on_ui, open_path
from ui.sidebar import Sidebar
from ui.theme import P
from ui.tile import TILE_ASPECT, TILE_WIDTH, TileActions, build_tile

MENU_WIDTH = 390   # Menüeinträge sonst so schmal wie die Menüleiste - Texte würden abgeschnitten
MOBILE_MENU_WIDTH = 290
SEARCH_DELAY_SECONDS = 0.2   # Suche erst nach kurzer Tipp-Pause auswerten
COLOR_OPTIONS = (
    ("voe1", "VÖ +1 (Beendet/TBA/Gestoppt/NA)"),
    ("komplett_beendet", "Komplett/Beendet"),
    ("verlag", "Verlag"),
    ("bestellt", "Titel bestellt (hellblau)"),
    ("angekommen", "Titel angekommen (abholbereit)"),
)


def _separator():
    """Senkrechter Trennstrich der Werkzeugleiste (feste Höhe - ein
    VerticalDivider hätte in einer umbrechenden Zeile keine)."""
    return ft.Container(width=1, height=28, bgcolor=P.border, margin=ft.Margin.symmetric(horizontal=4))


def _handler(func):
    """on_click-Handler für eine Funktion ohne Argumente (auch async)."""
    if inspect.iscoroutinefunction(func):
        async def run_async(_e=None):
            await func()
        return run_async
    return lambda _e=None: func()


class MangaApp(CoverActions, DataActions, LookupActions):
    def __init__(self, page: ft.Page, on_closed=None):
        self.page = page
        self.mobile = is_mobile(page)
        self.on_closed = on_closed   # wird aufgerufen, sobald das Fenster endgültig geschlossen wird
        self.config_problem = config.problem()   # beschädigte config.json -> Hinweis nach dem Start
        config.ensure_file_exists()
        changelog.archive_old_entries()
        changelog.prune_isbn_logs()
        changelog.prune_order_logs()
        db.init_db()
        self.buffer = LibraryBuffer(db.load_all())   # Zwischenspeicher bis "Speichern"
        self._init_covers()
        self._ui_lock = threading.RLock()   # Kacheln werden auch aus Hintergrund-Threads neu gezeichnet
        self._closing = False
        self._search_timer = None
        self._mail_passwords = {}           # nur im Arbeitsspeicher, nie auf Platte
        self.selected_id = None
        self.sort_column = "titel"
        self.sort_reverse = False
        self.colors_enabled = config.get_dict("colors_enabled")
        self.tile_actions = TileActions(
            select=self.select, edit=self.edit_entry, plus_baende=self.increment_baende,
            plus_gelesen=self.increment_gelesen, context_items=self._context_items,
            long_press=self._show_context_sheet if self.mobile else None,
        )

        page.title = APP_TITLE
        theme.apply(page)
        if self.mobile:
            page.padding = ft.Padding.symmetric(horizontal=6, vertical=4)
            page.on_app_lifecycle_state_change = self._on_lifecycle
        else:
            page.padding = 8
            page.window.width = 1450
            page.window.height = 900
            page.window.min_width = 900
            page.window.min_height = 560
            page.window.prevent_close = True
            page.window.on_event = self._on_window_event
        page.on_keyboard_event = self._on_key
        page.on_resize = lambda _e: self._apply_sidebar_width()
        page.on_platform_brightness_change = self._on_brightness_change
        self._log_lines = []   # Live-Log der Sitzung - übersteht einen Neuaufbau (Farbschema)

        self._build()
        self.refresh()
        if config.get_bool("cover_auto_lookup", True):
            import covers

            self.start_cover_job(covers.pending(self.buffer.data, self.covers), startup=True)
        if self.config_problem:
            alert(page, "Konfiguration",
                  f"Die Datei config.json ist beschädigt ({self.config_problem}).\n\n"
                  "Es gelten vorerst die Standardwerte. Sobald eine Einstellung geändert wird, "
                  "wird die beschädigte Datei als config.json.defekt aufbewahrt.")

    # ================================================================ Aufbau

    def _build(self):
        self.menubar = self._build_menu_bar()

        self.undo_btn = ft.OutlinedButton("Rückgängig", icon=ft.Icons.UNDO, on_click=_handler(self.undo),
                                          tooltip="Letzte Änderung rückgängig machen (Strg+Z)")
        self.redo_btn = ft.OutlinedButton("Wiederholen", icon=ft.Icons.REDO, on_click=_handler(self.redo),
                                          tooltip="Rückgängig gemachte Änderung wiederholen (Strg+Y)")
        self.save_btn = ft.FilledButton(
            "Speichern", icon=ft.Icons.SAVE, on_click=_handler(self.save),
            style=ft.ButtonStyle(bgcolor="#4CAF50", color="#FFFFFF"),
            tooltip="Alle Änderungen dauerhaft in der Datenbank speichern (Strg+S)",
        )
        upload_btn = ft.OutlinedButton("Zu Google Drive sichern", icon=ft.Icons.CLOUD_UPLOAD,
                                       on_click=_handler(self.drive_upload))
        sync_btn = ft.OutlinedButton("Geräte-Abgleich", icon=ft.Icons.SYNC, on_click=_handler(self.open_device_sync),
                                     tooltip="Mit Handy, Tablet oder einem anderen PC im selben WLAN abgleichen")
        isbn_btn = ft.OutlinedButton("ISBN-Abgleich / Bestellliste", icon=ft.Icons.SEARCH,
                                     on_click=_handler(self.open_isbn_lookup))
        vlb_btn = ft.OutlinedButton(
            "VÖ-Termine holen", icon=ft.Icons.EVENT, on_click=_handler(self.start_vlb_lookup),
            tooltip="Fragt bei buchhandel.de die Termine neuer Bände ab und trägt sie rot in VÖ +1 bis VÖ +3 ein "
                    "(gültig erst nach Speichern)",
        )

        self.verlag_filter = self._dropdown("Verlag", [gallery.FILTER_ALL], 190)
        self.voe1_filter = self._dropdown("VÖ +1", gallery.VOE1_FILTER_OPTIONS, 140)
        self.order_filter = self._dropdown("Bestellung", list(logic.ORDER_FILTER_OPTIONS), 200)
        self.order_filter.tooltip = ("Nach Bestell-Markierung filtern:\nBestellt = Schild „bestellt“, "
                                     "Angekommen = Schild „abholbereit“,\nNicht bestellt = keine der beiden.")
        self.typ_filter = self._dropdown("Typ", [gallery.FILTER_ALL], 140)
        self.sort_choice = ft.Dropdown(
            label="Sortierung", value="titel", width=210, dense=True,
            options=[ft.DropdownOption(key=k, text=label) for k, label in gallery.SORT_OPTIONS],
            on_select=lambda _e: self._refresh_tiles(),
        )
        self.sort_dir_btn = ft.IconButton(ft.Icons.ARROW_UPWARD, tooltip="Aufsteigend - klicken zum Umkehren",
                                          on_click=_handler(self._toggle_sort_direction))
        reset_btn = ft.TextButton("Filter zurücksetzen", on_click=_handler(self._reset_filters))
        calendar_btn = ft.OutlinedButton(
            "VÖ-Kalender", icon=ft.Icons.CALENDAR_MONTH, on_click=_handler(self.open_calendar),
            tooltip="Veröffentlichungen eines Monats, nach Erscheinungstag (Strg+K)",
        )

        filter_controls = [self.verlag_filter, self.voe1_filter, self.order_filter, self.typ_filter,
                           self.sort_choice, self.sort_dir_btn, reset_btn]
        if self.mobile:
            # Handy: eine wischbare Zeile statt umbrechender Reihen
            filters = ft.Row(filter_controls, spacing=8, scroll=ft.ScrollMode.AUTO,
                             vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            toolbar = ft.Row(
                [self.undo_btn, self.redo_btn, _separator(), self.save_btn, _separator(),
                 upload_btn, sync_btn, _separator(), isbn_btn, vlb_btn, calendar_btn],
                spacing=6, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            filters = ft.Row(filter_controls, spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self.grid = ft.GridView(
            expand=True, max_extent=TILE_WIDTH, child_aspect_ratio=TILE_ASPECT, spacing=14, run_spacing=14,
            padding=ft.Padding.only(top=4, bottom=12, right=8, left=4),
        )
        self.search_field = ft.TextField(dense=True, expand=True, prefix_icon=ft.Icons.SEARCH, bgcolor=P.surface,
                                         on_change=self._on_search_change)
        self.sidebar = Sidebar(self.search_field, on_open_month=self._open_calendar_month,
                               with_search=not self.mobile)
        self.sidebar_box = ft.Container(self.sidebar.control, width=300)

        self.status_text = ft.Text(size=12)
        self.cover_status = ft.Text(size=12, color=P.text_muted, visible=False)
        self.cover_cancel_btn = ft.TextButton("Abbrechen", visible=False, on_click=_handler(self.cancel_cover_job),
                                              style=ft.ButtonStyle(padding=4))
        self.legend = self._build_legend()

        for line in self._log_lines:
            self.sidebar.log(line)
        if self.mobile:
            self._build_mobile(filters)
            return
        footer = ft.Row(
            [self.status_text, self.cover_status, self.cover_cancel_btn,
             ft.Container(self.legend, expand=True, alignment=ft.Alignment.CENTER_RIGHT)],
            spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.page.add(ft.Column(
            [
                self.menubar,
                toolbar,
                filters,
                ft.Row([ft.Column([self.grid], expand=True), self.sidebar_box], expand=True,
                       vertical_alignment=ft.CrossAxisAlignment.STRETCH),
                footer,
            ],
            expand=True, spacing=6,
        ))
        self._apply_sidebar_width()

    def _build_mobile(self, filters):
        """Aufbau auf dem Handy: Symbolzeile mit Menü, Suche, wischbare
        Filterzeile, Kacheln, Statuszeile. Seitenleiste und Farblegende
        stehen in der „Übersicht“ (_show_overview)."""
        def icon_btn(icon, tooltip, func, **kwargs):
            return ft.IconButton(icon, tooltip=tooltip, on_click=_handler(func), **kwargs)

        # Rückgängig/Wiederholen/Speichern als Symbole; _refresh_chrome
        # schaltet sie wie die Knöpfe am PC
        self.undo_btn = icon_btn(ft.Icons.UNDO, "Rückgängig", self.undo)
        self.redo_btn = icon_btn(ft.Icons.REDO, "Wiederholen", self.redo)
        self.save_btn = icon_btn(ft.Icons.SAVE, "Speichern", self.save, icon_color="#4CAF50")
        top = ft.Row(
            [
                self.menubar,
                ft.Container(expand=True),
                self.undo_btn, self.redo_btn, self.save_btn,
                icon_btn(ft.Icons.ADD, "Neuer Eintrag", self.add_entry),
                icon_btn(ft.Icons.SYNC, "Geräte-Abgleich", self.open_device_sync),
                icon_btn(ft.Icons.INSIGHTS, "Übersicht (Statistik, Termine, Legende)", self._show_overview),
            ],
            spacing=0, scroll=ft.ScrollMode.AUTO, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.grid.max_extent = TILE_WIDTH - 20
        footer = ft.Row([self.status_text, self.cover_status, self.cover_cancel_btn], spacing=8, wrap=True)
        self.page.add(ft.SafeArea(ft.Column(
            [top, ft.Row([self.search_field]), filters, self.grid, footer],
            expand=True, spacing=4,
        ), expand=True))

    def _show_overview(self):
        """Handy: Seitenleiste (Statistik, Verlage, Typen, Termine, Live-Log)
        und Farblegende als Blatt von unten."""
        height = max(300, int((self.page.height or 700) * 0.8))
        self.sidebar.control.expand = True   # scrollt im Blatt selbst
        self.page.show_dialog(ft.BottomSheet(
            ft.Container(
                ft.Column([self.sidebar.control, ft.Divider(), self.legend], spacing=8, expand=True),
                padding=12, height=height,
            ),
            show_drag_handle=True, scrollable=True,
        ))

    def _show_context_sheet(self, row_id):
        """Handy: das Kontextmenü einer Kachel (langes Drücken) als Blatt von
        unten - dieselben Einträge wie beim Rechtsklick am PC."""
        entry = self.buffer.find(row_id)
        if entry is None:
            return
        self.select(row_id)

        def tile_for(item: ft.PopupMenuItem):
            if item.content is None:
                return ft.Divider(height=1)

            async def click(e):
                close_dialog(self.page)
                result = item.on_click(e)
                if inspect.isawaitable(result):
                    await result

            return ft.ListTile(leading=ft.Icon(item.icon), title=ft.Text(item.content), on_click=click, dense=True)

        self.page.show_dialog(ft.BottomSheet(
            ft.Container(ft.Column(
                [ft.Text(entry.get("titel") or "(ohne Titel)", weight=ft.FontWeight.BOLD, size=16),
                 *[tile_for(item) for item in self._context_items(row_id)]],
                tight=True, spacing=0, scroll=ft.ScrollMode.AUTO,
            ), padding=12),
            show_drag_handle=True, scrollable=True,
        ))

    def _dropdown(self, label, options, width):
        return ft.Dropdown(
            label=label, value=options[0], width=width, dense=True,
            options=[ft.DropdownOption(key=o, text=o) for o in options],
            on_select=lambda _e: self._refresh_tiles(),
        )

    def _apply_sidebar_width(self):
        """Breite der Seitenleiste als Anteil der Fensterbreite
        (sidebar_width_fraction, wie in Version 1), mindestens 280 Pixel."""
        if self.mobile:
            return
        try:
            fraction = max(0.05, min(0.6, config.get_float("sidebar_width_fraction", 0.15)))
            width = self.page.width or self.page.window.width or 1400
            self.sidebar_box.width = max(280, min(600, int(width * fraction)))
        except (TypeError, ValueError, OverflowError):
            self.sidebar_box.width = 300
        self.page.update()

    # -------------------------------------------------------------- Menüs

    @property
    def _menu_width(self):
        return MOBILE_MENU_WIDTH if self.mobile else MENU_WIDTH

    def _item(self, label, func, shortcut="", icon=None, tooltip=None):
        return ft.MenuItemButton(
            content=ft.Text(label), leading=ft.Icon(icon, size=18) if icon else ft.Container(width=18),
            trailing=ft.Text(shortcut, size=12, color=P.text_muted) if shortcut and not self.mobile else None,
            on_click=_handler(func), tooltip=None if self.mobile else tooltip, width=self._menu_width,
        )

    def _check_item(self, label, is_checked, toggle, tooltip=None):
        item = ft.MenuItemButton(content=ft.Text(label), tooltip=None if self.mobile else tooltip,
                                 close_on_click=False, width=self._menu_width)

        def sync():
            item.leading = ft.Icon(ft.Icons.CHECK_BOX if is_checked() else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                                   size=18)

        def click(_e):
            toggle(not is_checked())
            sync()
            self.page.update()

        item.on_click = click
        sync()
        self._check_syncs.append(sync)
        return item

    def _build_menu_bar(self):
        self._check_syncs = []
        file_menu = ft.SubmenuButton(content=ft.Text("Datei"), controls=[
            self._item("Neuer Eintrag", self.add_entry, "Strg+N", ft.Icons.ADD),
            self._item("Bearbeiten", self.edit_entry, "Doppelklick", ft.Icons.EDIT),
            self._item("Löschen", self.delete_entry, icon=ft.Icons.DELETE_OUTLINE),
            ft.Divider(height=1),
            self._item("Bei buchhandel.de suchen", self.search_on_buchhandel, "Strg+B", ft.Icons.TRAVEL_EXPLORE,
                       "Den markierten Titel direkt auf buchhandel.de suchen (öffnet den Browser)"),
            self._item("VÖ-Termine von buchhandel.de holen …", self.start_vlb_lookup, icon=ft.Icons.EVENT,
                       tooltip="Neue Werte erscheinen rot in VÖ +1 bis VÖ +3 und werden erst mit Speichern "
                               "übernommen."),
            self._item("Veröffentlichungskalender …", self.open_calendar, "Strg+K", ft.Icons.CALENDAR_MONTH,
                       tooltip="Veröffentlichungen eines Monats, nach Erscheinungstag"),
            self._item("Cover neu suchen …", self.open_cover_refresh, icon=ft.Icons.IMAGE_SEARCH,
                       tooltip="Cover von Band 1 erneut bei DNB und VLB suchen"),
            ft.Divider(height=1),
            self._item("CSV importieren …", self.import_csv, icon=ft.Icons.FILE_UPLOAD),
            self._item("CSV exportieren …", self.export_csv, icon=ft.Icons.FILE_DOWNLOAD),
            self._item("Bestellung aus E-Mail (.eml) einlesen …", self.import_order_mails, icon=ft.Icons.MAIL,
                       tooltip="Liest Bestellbestätigungen (.eml) und markiert die bestellten Titel. "
                               "Die E-Mail selbst wird nicht gespeichert."),
            self._item("Bestellungen aus Postfach abrufen …", self.fetch_orders_from_mailbox,
                       icon=ft.Icons.MARK_EMAIL_UNREAD,
                       tooltip="Ruft Bestellbestätigungen per IMAP direkt aus dem Postfach ab (Zugang unter "
                               "Konfigurieren → Postfach). Es wird nichts im Postfach verändert."),
            ft.Divider(height=1),
            self._item("Geräte-Abgleich (WLAN) …", self.open_device_sync, icon=ft.Icons.SYNC,
                       tooltip="Mit Handy, Tablet oder einem anderen PC im selben WLAN abgleichen"),
            # Google-Anmeldung braucht einen Browser auf demselben Gerät - am Handy nicht
            *([] if self.mobile else [
                self._item("Von Google Drive laden", self.drive_download, icon=ft.Icons.CLOUD_DOWNLOAD)]),
            *([self._item("ISBN-Abgleich / Bestellliste …", self.open_isbn_lookup, icon=ft.Icons.SEARCH)]
              if self.mobile else []),
        ])
        colors_menu = ft.SubmenuButton(content=ft.Text("Farben"), leading=ft.Icon(ft.Icons.PALETTE, size=18),
                                       width=self._menu_width, controls=[
            self._check_item(label, lambda k=key: self.colors_enabled.get(k, True),
                             lambda checked, k=key: self._set_color(k, checked))
            for key, label in COLOR_OPTIONS
        ])
        theme_menu = ft.SubmenuButton(
            content=ft.Text("Darstellung"), leading=ft.Icon(ft.Icons.CONTRAST, size=18), width=self._menu_width,
            controls=[self._check_item(label, lambda m=key: theme.mode() == m,
                                       lambda _checked, m=key: self.set_theme(m))
                      for key, label in theme.THEME_OPTIONS],
        )
        config_menu = ft.SubmenuButton(content=ft.Text("Konfigurieren"), controls=[
            theme_menu,
            colors_menu,
            self._item("Konfiguration …", self.open_config, icon=ft.Icons.SETTINGS,
                       tooltip="Zentrale Konfigurationsdatei (config.json) bearbeiten"),
            self._item("Postfach (IMAP) …", self.open_mail_settings, icon=ft.Icons.ALTERNATE_EMAIL,
                       tooltip="Zugang und Suchfilter für den Abruf von Bestellbestätigungen"),
            ft.Divider(height=1),
            self._check_item(
                "Nach Bearbeitung zur Kachel springen", lambda: config.get_bool("follow_selection_after_edit"),
                lambda checked: config.set_value("follow_selection_after_edit", checked),
                "Wenn aktiv: springt die Ansicht nach dem Bearbeiten automatisch zur bearbeiteten Kachel.",
            ),
            self._check_item(
                "Gestoppt: keine Berechnung", lambda: config.get_bool("exclude_gestoppt_from_stats"),
                self._set_exclude_gestoppt,
                "Wenn aktiv: Titel mit VÖ +1 = „Gestoppt“ fließen nicht in die Statistik und die "
                "Gesamt/Gelesen/Offen-Bilanz je Typ ein.",
            ),
        ])
        help_menu = ft.SubmenuButton(content=ft.Text("Hilfe"), controls=[
            *([self._item("LOG-Ordner öffnen", self.open_log_folder, icon=ft.Icons.FOLDER_OPEN,
                          tooltip="Änderungsprotokoll, Protokolle von ISBN-Abgleich und Bestellungen, fehler.log"),
               ft.Divider(height=1)] if can_open_paths() else []),
            self._item(f"Über {APP_TITLE} …", self.open_about, icon=ft.Icons.INFO_OUTLINE),
        ])
        if self.mobile:
            # Handy: alle Menüs hinter einem Knopf
            for menu in (file_menu, config_menu, help_menu):
                menu.width = self._menu_width
            return ft.MenuBar(controls=[ft.SubmenuButton(content=ft.Icon(ft.Icons.MENU),
                                                         controls=[file_menu, config_menu, help_menu])],
                              style=ft.MenuStyle(bgcolor=P.surface, elevation=0))
        return ft.MenuBar(controls=[file_menu, config_menu, help_menu],
                          style=ft.MenuStyle(bgcolor=P.surface, elevation=0))

    def set_theme(self, mode: str):
        """Farbschema wechseln (siehe ui/theme.py) und das Fenster neu aufbauen."""
        config.set_value("theme_mode", mode)
        self._rebuild()

    def _on_brightness_change(self, _e):
        if theme.mode() == "system":
            self._rebuild()

    def _rebuild(self):
        theme.apply(self.page)
        with self._ui_lock:
            self.page.controls.clear()
            self._build()
            self.refresh()

    def _set_color(self, key, checked):
        enabled = dict(config.load().get("colors_enabled") or {})
        enabled[key] = checked
        config.set_value("colors_enabled", enabled)
        self.colors_enabled = config.get_dict("colors_enabled")
        self._refresh_tiles()

    def _set_exclude_gestoppt(self, checked):
        config.set_value("exclude_gestoppt_from_stats", checked)
        self.refresh()

    def open_config(self):
        from ui.dialogs import open_config_dialog

        def saved():
            self.colors_enabled = config.get_dict("colors_enabled")
            for sync in self._check_syncs:
                sync()
            self._apply_sidebar_width()
            self.refresh()

        open_config_dialog(self.page, saved)

    def open_about(self):
        from ui.dialogs import open_about_dialog

        open_about_dialog(self.page, db.DB_FILE.parent)

    def open_device_sync(self):
        """Geräte-Abgleich im WLAN (ui/sync_dialog.py). Abgeglichen wird der
        gespeicherte Stand - ungespeicherte Änderungen also vorher speichern."""
        from ui.sync_dialog import SyncDialog

        def open_dialog():
            SyncDialog(self, mobile=self.mobile)

        if self.buffer.dirty:
            ask(self.page, "Ungespeicherte Änderungen",
                "Abgeglichen wird der gespeicherte Stand. Jetzt speichern und fortfahren?",
                [("Speichern und fortfahren", lambda: self.save() and open_dialog(), True),
                 ("Abbrechen", None, False)])
            return
        open_dialog()

    def reload_after_sync(self, name, counts):
        """Nach einem Abgleich: Datenbank neu laden (der Zwischenspeicher war
        vorher gespeichert) und fehlende Cover suchen."""
        if not any(counts.get(k) for k in ("created", "updated", "deleted")):
            return
        from ui.sync_dialog import summary

        self.buffer.load(db.load_all())
        self.selected_id = None
        self.refresh()
        self._log(f"Geräte-Abgleich mit {name}: {summary(counts)}.")
        if config.get_bool("cover_auto_lookup", True):
            import covers

            self.start_cover_job(covers.pending(self.buffer.data, self.covers), startup=True)

    def open_calendar(self, year=None, month=None):
        from ui.calendar_dialog import CalendarDialog

        CalendarDialog(self, year, month)

    def _open_calendar_month(self, offset: int):
        today = date.today()
        self.open_calendar(*release_calendar.shift_month(today.year, today.month, offset))

    def open_log_folder(self):
        try:
            changelog.LOG_DIR.mkdir(parents=True, exist_ok=True)
            open_path(changelog.LOG_DIR)
        except OSError as exc:
            alert(self.page, "LOG-Ordner", f"Der Ordner konnte nicht geöffnet werden:\n{exc}")

    # ---------------------------------------------------------- Legende

    @staticmethod
    def _swatch(color, label, border=None):
        box = ft.Container(width=14, height=14, bgcolor=color, border=ft.Border.all(1, "#888888"))
        if border:
            box = ft.Container(width=20, height=14, border_radius=3, bgcolor=P.surface,
                               border=ft.Border.all(3, border))
        return ft.Row([box, ft.Text(label, size=12)], spacing=4, tight=True)

    def _build_legend(self):
        """Farblegende wie in Version 1 (VÖ +1, Komplett/Beendet, Verlag,
        bestellt, angekommen, VÖ neu) und die Rahmenfarben der Kacheln."""
        self.border_legend = ft.Row(spacing=8, tight=True)
        return ft.Row(
            [
                ft.Text("VÖ +1:", size=12),
                *[self._swatch(colors.VOE1_STATUS_COLORS[k], label) for k, label in
                  (("beendet", "Beendet"), ("tba", "TBA"), ("gestoppt", "Gestoppt"), ("na", "NA"))],
                ft.Text("Komplett/Beendet:", size=12),
                self._swatch(colors.JA_NEIN_COLORS["ja"], "Ja"),
                self._swatch(colors.JA_NEIN_COLORS["nein"], "Nein"),
                ft.Text("Verlag: automatische Farbe je Verlag", size=12),
                self._swatch(colors.BESTELLT_COLOR, "bestellt"),
                self._swatch(colors.ANGEKOMMEN_COLOR, "abholbereit"),
                ft.Text("VÖ neu", size=12, color=colors.NEW_VALUE_TEXT_COLOR,
                        tooltip="Rote Schrift: von buchhandel.de eingetragen, noch nicht gespeichert"),
                ft.Text("Rahmen:", size=12),
                self.border_legend,
            ],
            spacing=8, wrap=True,
        )

    def _refresh_border_legend(self):
        counts = gallery.status_counts(self.buffer.data)
        self.border_legend.controls = [
            self._swatch(None, f"{label} ({counts[label]})", gallery.STATUS_BORDER_COLORS[key])
            for key, label in gallery.STATUS_LABELS.items()
        ]

    # ============================================================ Anzeige

    def refresh(self):
        """Alles neu: Filterauswahl, Verlagsfarben, Seitenleiste, Kacheln."""
        verlage = self.buffer.distinct_values("verlag")
        colors.set_verlag_universe(verlage)
        self._set_options(self.verlag_filter, [gallery.FILTER_ALL, *verlage])
        self._set_options(self.typ_filter, [gallery.FILTER_ALL, *self.buffer.distinct_values("typ")])
        self.sidebar.update(self.buffer.data, config.get_bool("exclude_gestoppt_from_stats"))
        self._refresh_tiles()

    @staticmethod
    def _set_options(dropdown, values):
        if dropdown.value not in values:
            dropdown.value = values[0]
        dropdown.options = [ft.DropdownOption(key=v, text=v) for v in values]

    def _shown_entries(self):
        return gallery.visible_entries(
            self.buffer.data,
            search=self.search_field.value or "",
            verlag=self.verlag_filter.value or gallery.FILTER_ALL,
            voe1=self.voe1_filter.value or gallery.FILTER_ALL,
            order=self.order_filter.value or logic.ORDER_FILTER_ALL,
            typ=self.typ_filter.value or gallery.FILTER_ALL,
            sort_column=self.sort_choice.value or "titel",
            reverse=self.sort_reverse,
        )

    def _refresh_tiles(self):
        """Nur die Kacheln neu filtern/sortieren - die Seitenleiste hängt davon nicht ab."""
        shown = self._shown_entries()
        if self.selected_id is not None and all(e.get("id") != self.selected_id for e in shown):
            self.selected_id = None
        with self._ui_lock:
            self.grid.controls = [self._tile(e) for e in shown]
            self.status_text.value = f"{len(shown)} Einträge" + (
                "  —  ungespeicherte Änderungen" if self.buffer.dirty else "")
            self._refresh_border_legend()
            self._refresh_chrome()
            self.page.update()

    def _tile(self, entry):
        return build_tile(entry, self._image_for(entry.get("titel") or ""), self.tile_actions,
                          self.colors_enabled, selected=entry.get("id") == self.selected_id)

    def _refresh_chrome(self):
        dirty = self.buffer.dirty
        self.page.title = APP_TITLE + (" *" if dirty else "")
        self.undo_btn.disabled = not self.buffer.can_undo
        self.redo_btn.disabled = not self.buffer.can_redo
        self.status_text.color = colors.NEW_VALUE_TEXT_COLOR if dirty else P.text_muted

    def _replace_tile(self, row_id):
        """Nur die Kachel eines Eintrags neu zeichnen (Auswahl, "+1") - die
        Position bleibt, damit die Kachel nicht unter dem Mauszeiger wegspringt."""
        entry = self.buffer.find(row_id)
        with self._ui_lock:
            for i, control in enumerate(self.grid.controls):
                if control.data == row_id and entry is not None:
                    self.grid.controls[i] = self._tile(entry)
                    break
            self.page.update()

    def _replace_tiles_of(self, titel: str):
        """Kacheln mit diesem Titel neu zeichnen (nach einem neuen Cover)."""
        with self._ui_lock:
            for i, control in enumerate(self.grid.controls):
                entry = self.buffer.find(control.data)
                if entry is not None and (entry.get("titel") or "") == titel:
                    self.grid.controls[i] = self._tile(entry)
            self.page.update()

    def _after_change(self):
        """Nach jeder Änderung am Zwischenspeicher: alles neu anzeigen und -
        wenn eingestellt - zur ausgewählten Kachel springen."""
        self.refresh()
        if self.selected_id is not None and config.get_bool("follow_selection_after_edit"):
            self.page.run_task(self._scroll_to_selected)

    async def _scroll_to_selected(self):
        try:
            await self.grid.scroll_to(scroll_key=f"t{self.selected_id}", duration=300)
        except Exception:  # noqa: BLE001 - Kachel gerade nicht sichtbar (Filter): dann eben nicht springen
            pass

    def _on_search_change(self, _e):
        if self._search_timer is not None:
            self._search_timer.cancel()
        self._search_timer = threading.Timer(SEARCH_DELAY_SECONDS, on_ui, (self.page, self._refresh_tiles))
        self._search_timer.start()

    def _toggle_sort_direction(self):
        self.sort_reverse = not self.sort_reverse
        self.sort_dir_btn.icon = ft.Icons.ARROW_DOWNWARD if self.sort_reverse else ft.Icons.ARROW_UPWARD
        self.sort_dir_btn.tooltip = ("Absteigend" if self.sort_reverse else "Aufsteigend") + " - klicken zum Umkehren"
        self._refresh_tiles()

    def _reset_filters(self):
        self.verlag_filter.value = gallery.FILTER_ALL
        self.voe1_filter.value = gallery.FILTER_ALL
        self.order_filter.value = logic.ORDER_FILTER_ALL
        self.typ_filter.value = gallery.FILTER_ALL
        self.search_field.value = ""
        self._refresh_tiles()

    def _toast(self, text):
        self.page.show_dialog(ft.SnackBar(ft.Text(text), duration=2500))

    def _log(self, message: str):
        """Dauerhaft ins Änderungsprotokoll (changelog.py) und live in die Seitenleiste."""
        line = changelog.log_change(message)
        self._log_lines.append(line)
        self.sidebar.log(line)
        self.page.update()

    # ============================================================ Auswahl

    def select(self, row_id):
        previous, self.selected_id = self.selected_id, row_id
        if previous is not None and previous != row_id:
            self._replace_tile(previous)
        self._replace_tile(row_id)

    def _entry_or_hint(self, row_id=None):
        """Eintrag zu `row_id` bzw. der ausgewählten Kachel - sonst ein Hinweis."""
        entry = self.buffer.find(row_id if row_id is not None else self.selected_id)
        if entry is None:
            alert(self.page, "Hinweis", "Bitte zuerst einen Eintrag auswählen (Kachel anklicken).")
        return entry

    def _context_items(self, row_id):
        """Rechtsklickmenü einer Kachel - Aktionen für genau diesen Eintrag."""
        def item(label, icon, func):
            if inspect.iscoroutinefunction(func):
                async def click(_e):
                    self.select(row_id)
                    await func(row_id)
            else:
                def click(_e):
                    self.select(row_id)
                    func(row_id)
            return ft.PopupMenuItem(content=label, icon=icon, on_click=click)

        entry = self.buffer.find(row_id) or {}
        items = [
            item("Bei buchhandel.de suchen", ft.Icons.TRAVEL_EXPLORE, self.search_on_buchhandel),
            item("Neue VÖ-Termine abfragen", ft.Icons.EVENT, self.lookup_vlb_single),
        ]
        if entry.get("bestellt") or entry.get("angekommen"):
            items.append(item("Bestellt-/Angekommen-Markierung entfernen", ft.Icons.REMOVE_DONE, self.clear_marks))
        items += [
            ft.PopupMenuItem(),
            item("Cover erneut suchen", ft.Icons.IMAGE_SEARCH, self.cover_search),
            item("Eigenes Bild als Cover …", ft.Icons.FOLDER_OPEN, self.cover_pick),
        ]
        if self._image_for(entry.get("titel") or ""):
            items.append(item("Cover entfernen", ft.Icons.HIDE_IMAGE, self.cover_remove))
        items += [
            ft.PopupMenuItem(),
            item("Bearbeiten", ft.Icons.EDIT, self.edit_entry),
            item("Löschen", ft.Icons.DELETE_OUTLINE, self.delete_entry),
        ]
        return items

    # ========================================================= Bearbeiten

    def add_entry(self):
        from ui.dialogs import open_entry_dialog

        def save(values):
            entry = self.buffer.add(values)
            self.selected_id = entry["id"]
            self._after_change()
            self._log(f"Neuer Eintrag: „{entry.get('titel') or '(ohne Titel)'}“.")

        open_entry_dialog(self.page, "Neuer Eintrag", save, verlag_values=self.buffer.distinct_values("verlag"),
                          other_titles=self.buffer.titles_except())

    def edit_entry(self, row_id=None):
        from ui.dialogs import open_entry_dialog

        entry = self._entry_or_hint(row_id)
        if entry is None:
            return
        row_id = entry["id"]
        self.select(row_id)

        def save(values):
            updated = self.buffer.update(row_id, values)   # erreichte Bestell-Markierungen entfallen dabei
            if updated is None:
                return
            self.selected_id = row_id
            self._after_change()
            self._log(f"Bearbeitet: „{updated.get('titel') or '(ohne Titel)'}“.")

        open_entry_dialog(self.page, "Eintrag bearbeiten", save, initial=entry,
                          verlag_values=self.buffer.distinct_values("verlag"),
                          other_titles=self.buffer.titles_except(row_id))

    def delete_entry(self, row_id=None):
        entry = self._entry_or_hint(row_id)
        if entry is None:
            return

        def delete():
            self.buffer.delete(entry["id"])
            self.selected_id = None
            self._after_change()
            self._log(f"Gelöscht: „{entry['titel']}“.")

        confirm(self.page, "Löschen bestätigen", f"„{entry['titel']}“ wirklich löschen?", delete)

    def increment_baende(self, row_id):
        # Markierungen entfallen erst, wenn ihr Band erreicht ist; VÖ-Termine
        # rücken nach (siehe logic.increment_baende)
        new_value = self.buffer.increment_baende(row_id)
        if new_value is None:
            alert(self.page, "Hinweis", "„Bände (bis)“ enthält keine gültige Zahl.")
            return
        self._after_plus(row_id)
        self._log(f"„{self.buffer.find(row_id).get('titel')}“: Bände (bis) auf {new_value} erhöht.")

    def increment_gelesen(self, row_id):
        result = self.buffer.increment_gelesen(row_id)
        if result is None:
            alert(self.page, "Hinweis", "„Gelesen bis“ enthält keine gültige Zahl.")
            return
        if result == logic.EXCEEDS:
            alert(self.page, "Hinweis", "„Gelesen bis“ kann nicht über „Bände (bis)“ hinaus erhöht werden – "
                                        "du kannst nicht mehr Bände gelesen haben, als du besitzt.")
            return
        self._after_plus(row_id)
        self._log(f"„{self.buffer.find(row_id).get('titel')}“: Gelesen bis auf {result} erhöht.")

    def _after_plus(self, row_id):
        """Nach "+1": Seitenleiste und Statuszeile neu, die Kachel wird
        ausgewählt und nur sie neu gezeichnet - Filter und Sortierung greifen
        erst beim nächsten Neuaufbau, damit sie nicht unter dem Mauszeiger
        wegspringt."""
        self.sidebar.update(self.buffer.data, config.get_bool("exclude_gestoppt_from_stats"))
        self.status_text.value = f"{len(self.grid.controls)} Einträge" + (
            "  —  ungespeicherte Änderungen" if self.buffer.dirty else "")
        self._refresh_border_legend()
        self._refresh_chrome()
        self.select(row_id)

    def undo(self):
        if self.buffer.undo():
            self.selected_id = None
            self._after_change()
            self._log("Rückgängig gemacht.")

    def redo(self):
        if self.buffer.redo():
            self.selected_id = None
            self._after_change()
            self._log("Wiederholt.")

    def _on_lifecycle(self, e):
        """Handy: beim Wechsel in den Hintergrund speichern - Android darf die
        App dort jederzeit beenden, eine Rückfrage wie am PC gibt es nicht."""
        if e.state in (ft.AppLifecycleState.HIDE, ft.AppLifecycleState.PAUSE) and self.buffer.dirty:
            self.save()

    def save(self) -> bool:
        """Schreibt den kompletten Puffer in die Datenbank (vorher Sicherung
        nach BACKUP/). Bei einem Fehler bleibt der Puffer unverändert."""
        try:
            db.create_backup("vor-speichern")
        except Exception as exc:  # noqa: BLE001 - dem Nutzer die Ursache zeigen
            self._log(f"Sicherung vor dem Speichern fehlgeschlagen: {exc}")
        try:
            saved = db.replace_all(self.buffer.data)
        except Exception as exc:  # noqa: BLE001 - ein Speicherfehler darf die Änderungen nicht verschlucken
            self._log(f"Speichern fehlgeschlagen: {exc}")
            alert(self.page, "Speichern fehlgeschlagen",
                  f"Die Datenbank konnte nicht gespeichert werden:\n\n{exc}\n\n"
                  "Die Änderungen sind weiterhin im Zwischenspeicher. Mögliche Ursache: Die Datei ist gerade von "
                  "einem anderen Programm gesperrt (z. B. Cloud-Synchronisierung oder Virenscanner). "
                  "Bitte später erneut speichern.")
            return False
        self.buffer.mark_saved(saved)
        self.selected_id = None
        self.refresh()
        self._toast(f"Gespeichert – {len(saved)} Einträge")
        self._log(f"Gespeichert ({len(saved)} Einträge).")
        return True

    # ===================================================== Tastatur/Ende

    def _on_key(self, e: ft.KeyboardEvent):
        if not e.ctrl:
            return
        key = (e.key or "").upper()
        if key == "S":
            self.save()
        elif key == "Z":
            self.redo() if e.shift else self.undo()
        elif key == "Y":
            self.redo()
        elif key == "N":
            self.add_entry()
        elif key == "B":
            self.search_on_buchhandel()
        elif key == "K":
            self.open_calendar()

    async def _close(self):
        """Fenster endgültig schließen - alles ist gespeichert oder bewusst
        verworfen. Flet wartet danach gelegentlich endlos auf das schon
        geschlossene Fenster; on_closed (main.py) beendet das Programm dann
        nach kurzer Frist selbst."""
        self._closing = True
        if self._cover_cancel is not None:
            self._cover_cancel.set()
        if self.on_closed:
            self.on_closed()
        await self.page.window.destroy()

    async def _on_window_event(self, e):
        if e.type != ft.WindowEventType.CLOSE:
            return
        if not self.buffer.dirty:
            await self._close()
            return

        async def answer(choice):
            close_dialog(self.page)
            if choice == "save" and not self.save():
                return   # Speichern fehlgeschlagen: Fenster offen lassen
            if choice in ("save", "discard"):
                await self._close()

        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Ungespeicherte Änderungen"),
            content=ft.Text("Es gibt ungespeicherte Änderungen. Vor dem Beenden speichern?"),
            actions=[
                ft.FilledButton("Speichern", on_click=lambda _e: self.page.run_task(answer, "save")),
                ft.TextButton("Nicht speichern", on_click=lambda _e: self.page.run_task(answer, "discard")),
                ft.TextButton("Abbrechen", on_click=lambda _e: self.page.run_task(answer, "cancel")),
            ],
        ))
