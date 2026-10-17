"""
ui/app.py
Das Hauptfenster: Werkzeugleiste (Rückgängig, Wiederholen, Speichern),
Filterleiste, Kachelansicht und Farblegende.

Wie in Version 1 bleiben alle Änderungen (z.B. die "+1"-Knöpfe) im
Zwischenspeicher (library.LibraryBuffer), bis gespeichert wird; vor dem
Speichern wird die Datenbank nach BACKUP/ gesichert.
"""

import flet as ft

import changelog
import config
import database as db
import gallery
import logic
from library import LibraryBuffer
from ui import APP_TITLE
from ui.tile import TILE_WIDTH, build_tile

PAGE_BG = "#F2F4F7"


class MangaApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config_problem = config.problem()   # beschädigte config.json -> Hinweis nach dem Start
        config.ensure_file_exists()
        changelog.archive_old_entries()
        changelog.prune_isbn_logs()
        changelog.prune_order_logs()
        db.init_db()
        self.buffer = LibraryBuffer(db.load_all())   # Zwischenspeicher bis "Speichern"

        page.title = APP_TITLE
        page.bgcolor = PAGE_BG
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 12
        page.window.width = 1400
        page.window.height = 900
        page.window.min_width = 700
        page.window.min_height = 500
        page.window.prevent_close = True
        page.window.on_event = self._on_window_event
        page.on_keyboard_event = self._on_key

        self._build()
        self.refresh()
        if self.config_problem:
            self._alert(
                "Konfiguration",
                f"Die Datei config.json ist beschädigt ({self.config_problem}).\n\n"
                "Es gelten vorerst die Standardwerte.",
            )

    # ------------------------------------------------------------ Aufbau

    def _build(self):
        self.undo_btn = ft.IconButton(ft.Icons.UNDO, tooltip="Rückgängig (Strg+Z)", on_click=lambda _e: self.undo())
        self.redo_btn = ft.IconButton(ft.Icons.REDO, tooltip="Wiederholen (Strg+Y)", on_click=lambda _e: self.redo())
        self.save_btn = ft.FilledButton("Speichern", icon=ft.Icons.SAVE, on_click=lambda _e: self.save())
        self.page.appbar = ft.AppBar(
            title=ft.Text(APP_TITLE, weight=ft.FontWeight.BOLD),
            bgcolor="#FFFFFF",
            actions=[self.undo_btn, self.redo_btn, ft.Container(self.save_btn, padding=ft.Padding.only(right=12))],
        )

        self.search = ft.TextField(
            hint_text="Suche (Titel, Verlag, Kommentar)", prefix_icon=ft.Icons.SEARCH, dense=True,
            width=320, on_change=lambda _e: self.refresh(), bgcolor="#FFFFFF",
        )
        self.typ_filter = self._dropdown("Typ", [gallery.FILTER_ALL])
        self.status_filter = self._dropdown("Status", [gallery.FILTER_ALL, *gallery.STATUS_LABELS.values()])
        self.sort_choice = self._dropdown("Sortierung", list(gallery.SORT_OPTIONS), width=230)
        self.count_text = ft.Text(color="#5F6673")
        filters = ft.Row(
            [self.search, self.typ_filter, self.status_filter, self.sort_choice, self.count_text],
            spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.grid = ft.GridView(
            expand=True, max_extent=TILE_WIDTH, child_aspect_ratio=0.5, spacing=14, run_spacing=14,
            padding=ft.Padding.only(top=4, bottom=12, right=8),
        )

        self.legend = ft.Row(spacing=18, wrap=True)
        self.page.add(ft.Column([filters, self.grid, self.legend], expand=True, spacing=10))

    def _dropdown(self, label, options, width=160):
        return ft.Dropdown(
            label=label, value=options[0], width=width, dense=True,
            options=[ft.DropdownOption(key=o, text=o) for o in options],
            on_select=lambda _e: self.refresh(),
        )

    # ---------------------------------------------------------- Anzeige

    def refresh(self):
        """Filter-Auswahl, Kacheln, Legende und Knöpfe neu aufbauen."""
        typen = [gallery.FILTER_ALL, *self.buffer.distinct_values("typ")]
        if self.typ_filter.value not in typen:
            self.typ_filter.value = gallery.FILTER_ALL
        self.typ_filter.options = [ft.DropdownOption(key=t, text=t) for t in typen]

        shown = gallery.visible_entries(
            self.buffer.data,
            search=self.search.value or "",
            typ=self.typ_filter.value or gallery.FILTER_ALL,
            status=self.status_filter.value or gallery.FILTER_ALL,
            order=self.sort_choice.value or gallery.SORT_TITEL,
        )
        self.grid.controls = [self._tile(e) for e in shown]
        self.count_text.value = f"{len(shown)} von {len(self.buffer.data)} Titeln"
        self._refresh_legend()
        self._refresh_chrome()
        self.page.update()

    def _tile(self, entry):
        return build_tile(entry, self.increment_baende, self.increment_gelesen)

    def _refresh_legend(self):
        counts = gallery.status_counts(self.buffer.data)
        items = []
        for key, label in gallery.STATUS_LABELS.items():
            items.append(ft.Row(
                [
                    ft.Container(width=22, height=14, border_radius=4,
                                 border=ft.Border.all(3, gallery.STATUS_BORDER_COLORS[key]), bgcolor="#FFFFFF"),
                    ft.Text(f"{label} ({counts[label]})", size=12, color="#3A3F48"),
                ],
                spacing=6,
                tight=True,
            ))
        self.legend.controls = items

    def _refresh_chrome(self):
        dirty = self.buffer.dirty
        self.page.title = APP_TITLE + (" *" if dirty else "")
        self.page.appbar.title.value = APP_TITLE + ("  •  ungespeicherte Änderungen" if dirty else "")
        self.undo_btn.disabled = not self.buffer.can_undo
        self.redo_btn.disabled = not self.buffer.can_redo
        self.save_btn.disabled = not dirty

    def _replace_tile(self, row_id):
        """Nur die Kachel eines Eintrags neu zeichnen (nach "+1") - die
        Position bleibt, damit die Kachel nicht unter dem Mauszeiger
        wegspringt. Filter und Sortierung greifen beim nächsten refresh()."""
        entry = self.buffer.find(row_id)
        for i, control in enumerate(self.grid.controls):
            if control.data == row_id and entry is not None:
                self.grid.controls[i] = self._tile(entry)
                break
        self._refresh_legend()
        self._refresh_chrome()
        self.page.update()

    def _toast(self, text):
        self.page.show_dialog(ft.SnackBar(ft.Text(text), duration=2500))

    def _alert(self, title, text):
        dialog = ft.AlertDialog(
            title=ft.Text(title), content=ft.Text(text),
            actions=[ft.TextButton("OK", on_click=lambda _e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)

    # --------------------------------------------------------- Aktionen

    def _title_of(self, row_id):
        entry = self.buffer.find(row_id)
        return (entry or {}).get("titel") or "(ohne Titel)"

    def increment_baende(self, row_id):
        # Markierungen entfallen erst, wenn ihr Band erreicht ist; VÖ-Termine
        # rücken nach (siehe logic.increment_baende)
        new_value = self.buffer.increment_baende(row_id)
        if new_value is None:
            self._alert("Hinweis", "„Bände (bis)“ enthält keine gültige Zahl.")
            return
        changelog.log_change(f"„{self._title_of(row_id)}“: Bände (bis) auf {new_value} erhöht.")
        self._replace_tile(row_id)
        self._toast(f"„{self._title_of(row_id)}“: Besitz {new_value}")

    def increment_gelesen(self, row_id):
        result = self.buffer.increment_gelesen(row_id)
        if result is None:
            self._alert("Hinweis", "„Gelesen bis“ enthält keine gültige Zahl.")
            return
        if result == logic.EXCEEDS:
            self._alert(
                "Hinweis",
                "„Gelesen bis“ kann nicht über „Bände (bis)“ hinaus erhöht werden – "
                "du kannst nicht mehr Bände gelesen haben, als du besitzt.",
            )
            return
        changelog.log_change(f"„{self._title_of(row_id)}“: Gelesen bis auf {result} erhöht.")
        self._replace_tile(row_id)
        self._toast(f"„{self._title_of(row_id)}“: gelesen bis {result}")

    def undo(self):
        if self.buffer.undo():
            self.refresh()
            self._toast("Rückgängig gemacht.")

    def redo(self):
        if self.buffer.redo():
            self.refresh()
            self._toast("Wiederholt.")

    def save(self) -> bool:
        """Schreibt den kompletten Puffer in die Datenbank (vorher Sicherung
        nach BACKUP/). Bei einem Fehler bleibt der Puffer erhalten."""
        try:
            db.create_backup("vor-speichern")
        except Exception as exc:  # noqa: BLE001 - dem Nutzer die Ursache zeigen
            changelog.log_change(f"Sicherung vor dem Speichern fehlgeschlagen: {exc}")
        try:
            saved = db.replace_all(self.buffer.data)
        except Exception as exc:  # noqa: BLE001 - ein Speicherfehler darf die Änderungen nicht verschlucken
            changelog.log_change(f"Speichern fehlgeschlagen: {exc}")
            self._alert(
                "Speichern fehlgeschlagen",
                f"Die Datenbank konnte nicht gespeichert werden:\n\n{exc}\n\n"
                "Die Änderungen sind weiterhin im Zwischenspeicher. Bitte später erneut speichern.",
            )
            return False
        self.buffer.mark_saved(saved)
        changelog.log_change(f"Gespeichert ({len(saved)} Einträge).")
        self.refresh()
        self._toast(f"Gespeichert – {len(saved)} Einträge")
        return True

    # ----------------------------------------------------- Tastatur/Ende

    def _on_key(self, e: ft.KeyboardEvent):
        if not e.ctrl:
            return
        key = (e.key or "").upper()
        if key == "S":
            self.save()
        elif key == "Z":
            self.undo()
        elif key == "Y":
            self.redo()

    async def _on_window_event(self, e):
        if e.type != ft.WindowEventType.CLOSE:
            return
        if not self.buffer.dirty:
            await self.page.window.destroy()
            return

        async def answer(choice):
            self.page.pop_dialog()
            if choice == "save" and not self.save():
                return   # Speichern fehlgeschlagen: Fenster offen lassen
            if choice in ("save", "discard"):
                await self.page.window.destroy()

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
