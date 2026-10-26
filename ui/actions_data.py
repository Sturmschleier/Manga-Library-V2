"""
ui/actions_data.py
Daten-Aktionen des Hauptfensters (Mixin für ui.app.MangaApp), wie in
Version 1: CSV-Import/-Export, Bestellungen aus E-Mail-Dateien (.eml) und
aus dem Postfach (IMAP), Google-Drive-Sicherung und -Download.

Wie in Version 1 landet alles zuerst im Zwischenspeicher; gespeichert wird
erst mit "Speichern". Ziehen und Ablegen von .eml-Dateien auf das Fenster
gibt es in Flet nicht - dafür lassen sich im Dateidialog mehrere Dateien
auf einmal wählen.
"""

import csv
import os

import flet as ft

import changelog
import covers
import csv_export
import database as db
import import_csv
import mail_fetch
import order_mail
from ui.common import Busy, alert, ask, prompt_password, run_background

_DRIVE_HINT = "Falls sich ein Browserfenster zur Google-Anmeldung öffnet, bitte dort anmelden."


class DataActions:
    # ------------------------------------------------------------------ CSV

    async def import_csv(self):
        files = await ft.FilePicker().pick_files(
            dialog_title="CSV-Datei auswählen", file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["csv"],
        )
        if not files or not files[0].path:
            return
        path = files[0].path
        try:
            parsed, warnings = import_csv.parse_csv(path)
        except (ValueError, OSError, csv.Error) as exc:
            alert(self.page, "CSV-Import", f"Import abgebrochen:\n\n{exc}")
            return
        imported, skipped = self.buffer.import_entries(parsed)
        self._after_change()
        if imported:
            self._log(f"CSV-Import: {imported} neu importiert, {skipped} übersprungen ({path}).")
        message = (f"{imported} neu importiert, {skipped} übersprungen (bereits vorhanden).\n"
                   "Die Einträge sind noch nicht gespeichert – bitte auf „Speichern“ klicken.")
        alert(self.page, "Import", message, "\n".join(warnings))

    async def export_csv(self):
        if self.mobile:
            await self._export_csv_mobile()
            return
        path = await ft.FilePicker().save_file(
            dialog_title="CSV-Export speichern unter", file_name="manga_library_export.csv",
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["csv"],
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            count = csv_export.export_csv(path, self.buffer.data)
        except OSError as exc:
            alert(self.page, "CSV-Export", f"Export fehlgeschlagen:\n\n{exc}")
            return
        alert(self.page, "CSV-Export", f"{count} Einträge wurden exportiert nach:\n{path}")

    async def _export_csv_mobile(self):
        """Handy: Der Speichern-Dialog von Android schreibt die Datei selbst
        und braucht dafür ihren Inhalt - die CSV entsteht deshalb zuerst als
        Zwischendatei im Datenordner."""
        tmp = db.DB_FILE.parent / "export_tmp.csv"
        try:
            count = csv_export.export_csv(str(tmp), self.buffer.data)
            data = tmp.read_bytes()
        except OSError as exc:
            alert(self.page, "CSV-Export", f"Export fehlgeschlagen:\n\n{exc}")
            return
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass   # nur Aufräumen
        path = await ft.FilePicker().save_file(
            dialog_title="CSV-Export speichern unter", file_name="manga_library_export.csv",
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["csv"], src_bytes=data,
        )
        if path:
            alert(self.page, "CSV-Export", f"{count} Einträge wurden exportiert.")

    # ---------------------------------------------------------- Bestellungen

    async def import_order_mails(self):
        files = await ft.FilePicker().pick_files(
            dialog_title="Bestellbestätigung(en) (E-Mail) auswählen", allow_multiple=True,
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["eml"],
        )
        paths = [f.path for f in files or [] if f.path]
        if not paths:
            return
        items, problems = [], []
        for path in paths:
            try:
                items += order_mail.parse_eml(path)
            except (ValueError, OSError) as exc:
                problems.append(f"{os.path.basename(path)}: {exc}")
        if not items:
            alert(self.page, "Bestellung einlesen",
                  "Aus den gewählten Dateien konnte keine Bestellung gelesen werden:\n\n" + "\n".join(problems))
            return
        self._apply_order_items(items, len(paths) - len(problems), "E-Mail-Datei(en)", problems)

    def _apply_order_items(self, items, mail_count, source, problems=()):
        """Ordnet die Artikel den Einträgen zu und markiert diese (bestellt
        bzw. angekommen, Wert = Bandnummer). Ins Log geht nur, welche Titel
        markiert wurden - nichts aus den E-Mails selbst."""
        matches, already_owned, unmatched = order_mail.match_items(items, self.buffer.data)
        new_matches = self.buffer.apply_order_matches(matches)
        new_ordered = [m for m in new_matches if m.item.kind == order_mail.KIND_ORDER]
        new_arrived = [m for m in new_matches if m.item.kind == order_mail.KIND_PICKUP]
        if new_matches:
            self._after_change()
            for label, group in (("bestellt", new_ordered), ("angekommen", new_arrived)):
                if group:
                    self._log(f"Bestellung eingelesen: {len(group)} Titel als {label} markiert ("
                              + ", ".join(f"{m.entry.get('titel')} Bd. {m.band}" for m in group) + ").")

        log_path, log_error = None, None
        try:
            log_path = changelog.write_order_log(order_mail.build_log(
                source, mail_count, items, matches, new_matches, already_owned, unmatched, problems,
            ))
        except OSError as exc:
            log_error = str(exc)

        lines = [f"{mail_count} E-Mail(s), {len(items)} Artikel, {len(matches)} Titel zugeordnet."]
        if new_ordered:
            lines.append(f"{len(new_ordered)} neu als bestellt markiert (hellblau).")
        if new_arrived:
            lines.append(f"{len(new_arrived)} neu als angekommen markiert (abholbereit).")
        if new_matches:
            lines.append("Noch nicht gespeichert – bitte auf „Speichern“ klicken.")
        if len(matches) > len(new_matches):
            lines.append(f"{len(matches) - len(new_matches)} waren bereits markiert.")
        if already_owned:
            lines.append(f"{len(already_owned)} Band/Bände waren schon im Bestand.")
        if unmatched:
            lines.append(f"{len(unmatched)} Artikel ohne passenden Eintrag (z. B. Sonderausgaben).")
        if problems:
            lines.append(f"{len(problems)} Datei(en) nicht lesbar.")
        if log_path:
            lines.append(f"Protokoll: {log_path}")
        elif log_error:
            lines.append(f"Protokoll konnte nicht geschrieben werden: {log_error}")

        details = []
        if already_owned:
            details += ["Bereits im Bestand (nicht markiert):",
                        *[f"  {m.entry.get('titel')} – Band {m.band}" for m in already_owned], ""]
        if unmatched:
            details += ["Keinem Eintrag zugeordnet:", *[f"  {item.name}" for item in unmatched], ""]
        if problems:
            details += ["Nicht lesbar:", *[f"  {p}" for p in problems]]
        alert(self.page, "Bestellung einlesen", "\n".join(lines), "\n".join(details).strip())

    def open_mail_settings(self):
        from ui.mail_dialogs import open_mail_settings_dialog

        open_mail_settings_dialog(self.page)

    def fetch_orders_from_mailbox(self):
        settings = mail_fetch.load_settings()
        if not settings.configured:
            alert(self.page, "Postfach",
                  "Der Postfach-Zugang ist noch nicht eingerichtet.\n\n"
                  "Bitte unter „Konfigurieren → Postfach (IMAP) …“ Server und Benutzername eintragen.")
            return
        password = self._mail_passwords.get(settings.credential_key) or mail_fetch.get_saved_password(settings)
        if password:
            self._fetch_mailbox(settings, password)
        else:
            prompt_password(self.page, "Postfach", f"Passwort für {settings.user}\n({settings.host}):",
                            lambda pw: self._fetch_mailbox(settings, pw))

    def _fetch_mailbox(self, settings, password):
        from ui.mail_dialogs import open_mail_select_dialog

        self._mail_passwords[settings.credential_key] = password   # nur im Arbeitsspeicher
        busy = Busy(self.page, "Postfach", "Rufe Bestellbestätigungen aus dem Postfach ab …")

        def done(mails, error):
            busy.close()
            if error is not None:
                self._mail_passwords.pop(settings.credential_key, None)   # evtl. falsches Passwort verwerfen
                alert(self.page, "Postfach", str(error))
                return
            if not mails:
                alert(self.page, "Postfach",
                      f"Keine passenden Mails gefunden (Ordner „{settings.folder}“, letzte {settings.days_back} "
                      f"Tage, Absender „{settings.sender or 'egal'}“, Betreff „{settings.subject or 'egal'}“).\n\n"
                      "Filter unter „Konfigurieren → Postfach (IMAP) …“ anpassbar.")
                return
            if not any(m.items for m in mails):
                alert(self.page, "Postfach",
                      f"{len(mails)} Mail(s) gefunden, aber keine enthält eine auswertbare Artikelliste.")
                return
            open_mail_select_dialog(self.page, mails, lambda chosen: self._apply_order_items(
                [item for m in chosen for item in m.items], len(chosen), "Postfach (IMAP)"))

        run_background(self.page, lambda: mail_fetch.fetch_orders(settings, password), done)

    def clear_marks(self, row_id):
        entry = self.buffer.find(row_id)
        if entry is None or not (entry.get("bestellt") or entry.get("angekommen")):
            return
        entry = self.buffer.clear_marks(row_id)
        self._after_change()
        self._log(f"Bestellt-/Angekommen-Markierung entfernt: „{entry.get('titel')}“.")

    # --------------------------------------------------------- Google Drive

    def _drive_sync(self):
        try:
            import drive_sync
        except ImportError as exc:
            alert(self.page, "Google Drive", f"Die Google-Bibliotheken fehlen ({exc}).")
            return None
        return drive_sync

    def drive_upload(self):
        if self.buffer.dirty:
            ask(self.page, "Ungespeicherte Änderungen",
                "Es gibt ungespeicherte Änderungen. Diese müssen zuerst lokal gespeichert werden, bevor zu "
                "Google Drive gesichert werden kann. Jetzt speichern und fortfahren?",
                [("Ja", lambda: self.save() and self._drive_upload(), False), ("Nein", None, True)])
            return
        self._drive_upload()

    def _drive_upload(self):
        drive_sync = self._drive_sync()
        if drive_sync is None:
            return
        busy = Busy(self.page, "Google Drive", f"Sichere zu Google Drive ...\n{_DRIVE_HINT}")

        def done(_result, error):
            busy.close()
            if error is not None:
                alert(self.page, "Google Drive", str(error))
                return
            self._log("Zu Google Drive gesichert.")
            alert(self.page, "Google Drive", "Datenbank wurde erfolgreich zu Google Drive gesichert.")

        run_background(self.page, drive_sync.upload, done)

    def drive_download(self):
        warning = "Die lokale Datenbank wird durch die Version aus Google Drive ersetzt. Fortfahren?"
        if self.buffer.dirty:
            warning = "Ungespeicherte Änderungen gehen dabei verloren!\n\n" + warning
        ask(self.page, "Google Drive", warning, [("Ja", self._drive_download, False), ("Nein", None, True)])

    def _drive_download(self):
        drive_sync = self._drive_sync()
        if drive_sync is None:
            return
        busy = Busy(self.page, "Google Drive", f"Lade von Google Drive ...\n{_DRIVE_HINT}")

        def done(backup_path, error):
            busy.close()
            if error is not None:
                alert(self.page, "Google Drive", str(error))
                return
            try:
                db.init_db()   # ältere Sicherung -> Schema ggf. auf den aktuellen Stand bringen
                self.buffer.load(db.load_all())
                covers.ensure_table()
                self.covers = covers.load_all()
                self._images.clear()
            except Exception as exc:  # noqa: BLE001 - dem Nutzer die Ursache zeigen
                alert(self.page, "Google Drive", f"Die geladene Datenbank konnte nicht geöffnet werden:\n\n{exc}")
                return
            self.selected_id = None
            self._after_change()
            message = "Datenbank wurde erfolgreich von Google Drive geladen."
            if backup_path:
                message += f"\n\nDie bisherige lokale Datenbank wurde gesichert unter:\n{backup_path}"
            self._log(f"Von Google Drive geladen ({len(self.buffer.data)} Einträge, Sicherung: {backup_path or '–'}).")
            alert(self.page, "Google Drive", message)

        run_background(self.page, drive_sync.download, done)
