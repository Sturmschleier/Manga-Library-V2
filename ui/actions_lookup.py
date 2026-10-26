"""
ui/actions_lookup.py
Abfragen bei DNB und buchhandel.de (Mixin für ui.app.MangaApp), wie in
Version 1: ISBN-Abgleich mit Bestellliste, VÖ-Termine von buchhandel.de
(alle bzw. ein einzelner Titel per Rechtsklick) und "Bei buchhandel.de
suchen" im Browser.
"""

import copy

import changelog
import database as db
from ui.common import Busy, alert, open_url, run_background


class LookupActions:
    # ------------------------------------------------ buchhandel.de im Browser

    def search_on_buchhandel(self, row_id=None):
        entry = self._entry_or_hint(row_id)
        if entry is None:
            return
        titel = (entry.get("titel") or "").strip()
        if not titel:
            return
        import isbn_lookup

        url = isbn_lookup.buchhandel_de_search_url(titel)
        if not open_url(url):
            alert(self.page, "buchhandel.de", f"Der Browser konnte nicht geöffnet werden:\n\n{url}")
            return
        self._toast(f"buchhandel.de: Suche nach „{titel}“ geöffnet.")

    # ---------------------------------------------------------- ISBN-Abgleich

    def open_isbn_lookup(self):
        from ui.isbn_dialogs import open_isbn_lookup_dialog

        open_isbn_lookup_dialog(self.page, self._start_isbn_lookup)

    def _start_isbn_lookup(self, selection):
        import isbn_lookup
        from ui.isbn_dialogs import open_isbn_result

        kind = selection[0]
        if kind == "month":
            _, month, year, overwrite = selection
            label = f"{month:02d}/{year}"
            only_month, only_status = (month, year), None
        else:
            _, status, overwrite = selection
            label = f"VÖ +1 = {status}"
            only_month, only_status = None, status
        if overwrite:
            label += " (inkl. bereits vorhandener ISBNs)"

        busy = Busy(self.page, "ISBN-Abgleich läuft ...", f"Suche ISBNs für {label} ...", cancellable=True,
                    cancel_text="Wird abgebrochen ...\nDer gerade laufende Titel wird noch fertig geprüft; "
                                "bereits gefundene ISBNs bleiben gespeichert.")
        # Gesucht wird im aktuellen Zwischenspeicher (auch ungespeicherte
        # Änderungen) - als Kopie, weil der Abgleich im Hintergrund läuft
        entries = copy.deepcopy(self.buffer.data)
        db_path = str(db.DB_FILE)

        def progress(done, total, titel):
            busy.progress(done, total, f"Suche ISBNs für {label} ...\nTitel {done + 1} von {total}: {titel}")

        def run():
            report = isbn_lookup.fill_missing_isbns(
                db_path, only_month=only_month, only_status=only_status, overwrite=overwrite,
                progress=progress, cancel=busy.cancel_event, entries=entries,
            )
            if kind == "month":
                liste = isbn_lookup.bestellliste_markdown(db_path, month, year, entries=entries)
            else:
                liste = isbn_lookup.bestellliste_markdown(db_path, status=status, entries=entries)
            return report, liste

        def done(result, error):
            busy.close()
            if error is not None:
                alert(self.page, "ISBN-Abgleich", f"Fehler beim Abgleich:\n\n{error}")
                return
            report, liste = result
            open_isbn_result(self.page, label + (" – abgebrochen" if report.abgebrochen else ""), report, liste)

        run_background(self.page, run, done)

    # ------------------------------------------- VÖ-Termine (buchhandel.de)

    def start_vlb_lookup(self):
        import vlb_lookup
        from ui.dialogs import open_vlb_dialog

        entries = copy.deepcopy(self.buffer.data)   # Abfrage im Hintergrund auf einer Kopie
        counts = vlb_lookup.count_by_scope(entries)
        if not counts[vlb_lookup.SCOPE_ALL]:
            alert(self.page, "VÖ-Termine", "Es gibt keine Serie, für die abgefragt werden muss.")
            return
        pause = vlb_lookup.REQUEST_DELAY_SECONDS + vlb_lookup.REQUEST_DELAY_JITTER_SECONDS / 2
        open_vlb_dialog(self.page, counts, pause, lambda scope: self._run_vlb_lookup(entries, scope, counts[scope]))

    def lookup_vlb_single(self, row_id):
        """Rechtsklick → "Neue VÖ-Termine abfragen": nur dieser Titel, ohne
        Überspringregel (wer ausdrücklich wählt, bekommt eine Abfrage)."""
        import vlb_lookup

        entry = self.buffer.find(row_id)
        if entry is None:
            return
        reason = vlb_lookup.unusable_reason(entry)
        if reason:
            alert(self.page, "VÖ-Termine", f"Für „{entry.get('titel', '')}“ nicht möglich: {reason}.")
            return
        self._run_vlb_lookup([copy.deepcopy(entry)], vlb_lookup.SCOPE_ALL, 1, single=True)

    def _run_vlb_lookup(self, entries, scope, todo, single=False):
        import vlb_lookup

        busy = Busy(self.page, "VÖ-Termine werden abgefragt ...", f"Frage {todo} Serien ab ...", cancellable=True,
                    cancel_text="Wird abgebrochen ...\nDie gerade laufende Abfrage wird noch fertig ausgewertet.")

        def run():
            return vlb_lookup.check_entries(
                entries, progress=lambda d, t, titel: busy.progress(d, t, f"Serie {d + 1} von {t}:\n{titel}"),
                cancel=busy.cancel_event, scope=scope, respect_skip=not single,
            )

        run_background(self.page, run,
                       lambda result, error: self._finish_vlb_lookup(busy, result, error, single, scope))

    @staticmethod
    def _single_vlb_message(r):
        found = ", ".join(f"Band {v.band}: {v.date.text()}" for v in r.volumes)
        if r.status == "neu":
            changes = ", ".join(f"{db.LABELS[c]} = {v}" for c, v in r.changes.items())
            return f"{r.titel}\n\nNeu eingetragen: {changes}\n\nRot, bis gespeichert wird."
        if r.status == "aktuell":
            return (f"{r.titel}\n\nKeine Änderung: Die Termine stimmen schon, oder der vorhandene Wert "
                    f"ist Freitext und bleibt unverändert.\n\nBei buchhandel.de gefunden: {found}.")
        if r.status == "keine_neuen":
            return f"{r.titel}\n\nKeine neuen Termine: {r.note or 'kein weiterer Band angekündigt'}."
        text = f"{r.titel}\n\n{r.note or 'kein Ergebnis'}."
        return text + (f"\n\nGefunden: {found}." if found else "")

    def _finish_vlb_lookup(self, busy, result, error, single=False, scope=None):
        import vlb_lookup

        busy.close()
        if error is not None:
            alert(self.page, "VÖ-Termine", f"Fehler bei der Abfrage:\n\n{error}")
            return
        results, cancelled = result
        applied = self.buffer.apply_vlb_dates(results)
        if applied:
            self._after_change()
        for r in applied:
            changes = ", ".join(f"{db.LABELS[col]} = {value}" for col, value in r.changes.items())
            self._log(f"VÖ-Abgleich buchhandel.de: {r.titel}: {changes}")

        try:
            log_note = "\n\nProtokoll: " + changelog.write_vlb_log(vlb_lookup.build_log(
                results, cancelled, applied, scope or vlb_lookup.SCOPE_ALL, single, db.LABELS))
        except OSError as exc:
            log_note = f"\n\nProtokoll konnte nicht geschrieben werden: {exc}"

        if single and results:
            r = results[0]
            if r.status == "fehler":
                alert(self.page, "VÖ-Termine", f"{r.titel}\n\nAbfrage nicht möglich: {r.note}." + log_note)
            else:
                alert(self.page, "VÖ-Termine", self._single_vlb_message(r) + log_note)
            return

        errors = [r for r in results if r.status == "fehler"]
        unclear = [r for r in results if r.status == "unklar"]
        lines = [f"{r.titel}: " + ", ".join(f"{db.LABELS[c]} {v}" for c, v in r.changes.items()) for r in applied]
        details = []
        if lines:
            details += ["Neue Termine (rot, noch nicht gespeichert):", *lines, ""]
        if unclear:
            details += ["Nicht eindeutig zuzuordnen (bitte bei Bedarf von Hand prüfen):",
                        *[f"{r.titel}: {r.note}" for r in unclear], ""]
        if errors:
            details += ["Fehler bei der Abfrage:", *[f"{r.titel}: {r.note}" for r in errors], ""]

        asked = sum(1 for r in results if r.status != "uebersprungen")
        text = f"{asked} Serien abgefragt, bei {len(applied)} neue Termine eingetragen."
        if cancelled:
            reason = " (mehrere Fehler in Folge)." if len(errors) >= vlb_lookup.MAX_CONSECUTIVE_ERRORS else "."
            text += "\n\nDer Abruf wurde vorzeitig beendet" + reason
        if applied:
            text += "\n\nDie neuen Werte sind rot und werden mit „Speichern“ übernommen."
        text += log_note
        alert(self.page, "VÖ-Termine", text, "\n".join(details).strip())
