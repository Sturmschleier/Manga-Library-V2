"""
ui/actions_covers.py
Cover-Aktionen des Hauptfensters (Mixin für ui.app.MangaApp): die Suche im
Hintergrund (nach dem Start für Titel ohne Cover, auf Wunsch für alle über
"Datei → Cover neu suchen …"), "Cover erneut suchen", eigenes Bild und
"Cover entfernen" im Rechtsklickmenü.

Gesucht wird Titel für Titel mit Pause (Fair Use bei DNB und VLB); es läuft
immer nur eine Suche gleichzeitig. Fortschritt und "Abbrechen" stehen unten
in der Statuszeile, jede fertige Kachel wird sofort neu gezeichnet.
"""

import threading
import time
from pathlib import Path

import flet as ft

import changelog
import covers
import vlb_lookup
from ui.common import alert, on_ui


class CoverActions:
    def _init_covers(self):
        covers.ensure_table()
        self.covers = covers.load_all()      # {titel: CoverInfo}
        self._images = {}                    # {titel: Bilddaten} - jede Datei nur einmal lesen
        self._cover_cancel = None            # threading.Event der laufenden Suche, sonst None

    def _image_for(self, titel: str):
        """Das Cover für die Kachel oder None: in der Desktop-App der
        Dateipfad (das Fenster liest die Datei selbst - sonst gingen bei
        jedem Neuaufbau alle Bilder als Daten durch die Verbindung), in der
        Browser-Vorschau die Bilddaten."""
        info = self.covers.get(titel)
        if info is None or info.quelle not in (*covers.FOUND_SOURCES, covers.QUELLE_EIGEN):
            return None
        if info.path is None:
            return None
        if not self.page.web:
            return str(info.path.resolve())
        if titel not in self._images:
            try:
                self._images[titel] = info.path.read_bytes()
            except OSError:
                return None
        return self._images[titel]

    def _set_cover(self, info: covers.CoverInfo):
        self.covers[info.titel] = info
        self._images.pop(info.titel, None)
        self._replace_tiles_of(info.titel)

    def _search_one(self, titel, verlag, typ, manuell=False):
        try:
            info = covers.lookup_and_store(titel, verlag, typ, manuell=manuell)
        except Exception as exc:  # noqa: BLE001 - ein Fehler bei einem Titel darf die Suche nicht beenden
            changelog.log_error(f"Cover-Suche für „{titel}“ fehlgeschlagen: {exc}")
            return None
        if not self._closing:
            on_ui(self.page, self._set_cover, info)   # läuft im Such-Thread
        return info

    # ------------------------------------------------- Suche im Hintergrund

    def start_cover_job(self, entries, startup: bool = False) -> bool:
        """Sucht die Cover der `entries` nacheinander im Hintergrund. False,
        wenn schon eine Suche läuft. Ohne `startup` von Hand angestoßen
        ("Cover neu suchen") - zählt beim Geräte-Abgleich wie ein eigenes Bild."""
        if self._cover_cancel is not None:
            return False
        todo = list(entries)
        if not todo:
            return True
        cancel = self._cover_cancel = threading.Event()

        def run():
            found = 0
            done = 0
            for done, entry in enumerate(todo, start=1):
                if cancel.is_set() or self._closing:
                    break
                on_ui(self.page, self._show_cover_status, f"Cover werden gesucht: {done} von {len(todo)} …", True)
                info = self._search_one(entry.get("titel") or "", entry.get("verlag"), entry.get("typ"),
                                        manuell=not startup)
                if info is not None and info.path:
                    found += 1
                time.sleep(vlb_lookup.REQUEST_DELAY_SECONDS)   # Fair Use bei DNB und VLB
            self._cover_cancel = None
            if self._closing:
                return
            ended = "abgebrochen" if cancel.is_set() else "fertig"
            on_ui(self.page, self._show_cover_status, f"Cover-Suche {ended}: {found} von {done} gefunden", False)
            if not startup:
                on_ui(self.page, self._log, f"Cover-Suche {ended}: {found} von {done} Titeln mit Cover.")
            time.sleep(8)
            if self._cover_cancel is None:
                on_ui(self.page, self._show_cover_status, "", False)

        self.page.run_thread(run)
        return True

    def _show_cover_status(self, text: str, running: bool):
        with self._ui_lock:
            self.cover_status.value = text
            self.cover_status.visible = bool(text)
            self.cover_cancel_btn.visible = running
            self.page.update()

    def cancel_cover_job(self):
        if self._cover_cancel is not None:
            self._cover_cancel.set()
            self._show_cover_status("Cover-Suche wird abgebrochen …", False)

    def open_cover_refresh(self):
        from ui.dialogs import open_cover_refresh_dialog

        if self._cover_cancel is not None:
            alert(self.page, "Cover neu suchen", "Es läuft bereits eine Cover-Suche (siehe Statuszeile unten).")
            return
        entries = self.buffer.data
        counts = {"fehlend": len(covers.refresh_targets(entries, self.covers)),
                  "alle": len(covers.refresh_targets(entries, self.covers, only_missing=False))}
        open_cover_refresh_dialog(self.page, counts, lambda only_missing: self.start_cover_job(
            covers.refresh_targets(self.buffer.data, self.covers, only_missing)))

    # ------------------------------------------------- Rechtsklickmenü

    def cover_search(self, row_id):
        entry = self.buffer.find(row_id)
        if entry is None:
            return
        titel = entry.get("titel") or ""
        self._toast(f"Suche Cover für „{titel}“ …")

        def run():
            info = self._search_one(titel, entry.get("verlag"), entry.get("typ"), manuell=True)
            if info is not None and info.path:
                quelle = covers.SOURCE_LABELS.get(info.quelle, info.quelle)
                isbn = f", ISBN {info.isbn}" if info.isbn else ""
                on_ui(self.page, self._toast, f"Cover für „{titel}“ gefunden ({quelle}{isbn}).")
            else:
                on_ui(self.page, self._toast,
                      f"Kein Cover für „{titel}“ gefunden – du kannst ein eigenes Bild wählen.")

        self.page.run_thread(run)

    async def cover_pick(self, row_id):
        entry = self.buffer.find(row_id)
        if entry is None:
            return
        files = await ft.FilePicker().pick_files(
            dialog_title=f"Cover für „{entry.get('titel')}“ wählen",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=list(covers.IMAGE_EXTENSIONS),
        )
        if not files:
            return
        if not files[0].path:
            alert(self.page, "Hinweis", "Ein eigenes Bild lässt sich nur in der Desktop-App wählen.")
            return
        try:
            info = covers.set_custom(entry.get("titel") or "", Path(files[0].path))
        except (OSError, ValueError) as exc:
            alert(self.page, "Bild nicht übernommen", str(exc))
            return
        self._set_cover(info)
        self._toast("Eigenes Cover übernommen.")

    def cover_remove(self, row_id):
        entry = self.buffer.find(row_id)
        if entry is None:
            return
        self._set_cover(covers.remove(entry.get("titel") or ""))
        self._toast("Cover entfernt – „Cover erneut suchen“ holt es zurück.")
