# Manga Library V2

[![Tests](https://github.com/Sturmschleier/Manga-Library-V2/actions/workflows/tests.yml/badge.svg)](https://github.com/Sturmschleier/Manga-Library-V2/actions/workflows/tests.yml)

Version 2 der Manga- & Light-Novel-Bibliothek, diesmal mit einer
[Flet](https://flet.dev)-Oberfläche. Statt einer Tabelle gibt es eine
Kachelansicht mit Covern, farbigen Statusrahmen und „+1“-Knöpfen.

Version 1 (Qt/PySide6) liegt weiter im eigenen Repository
[Manga-Bibliothek](https://github.com/Sturmschleier/Manga-Bibliothek). Beide
Versionen sind komplett getrennt. Die Datenbank (`manga_library.db`) hat
dasselbe Format und lässt sich also übernehmen.

> **Stand:** Entwicklungsversion mit allen Funktionen aus Version 1, als
> Kachelansicht. Es fehlen noch der Veröffentlichungskalender und das Release
> (siehe Fahrplan).

## Was geht

Aufbau wie in Version 1: Menüleiste, Werkzeugleiste mit Filtern, Kacheln statt
Tabelle, Seitenleiste rechts, Statuszeile mit Farblegende.

- **Kacheln:** alle gleich groß, mit dem Cover von Band 1 (ganz eingepasst),
  Titel, Verlag (Verlagsfarbe), Typ, Komplett/Beendet (grün/rot), Besitz und
  Gelesen mit „+1“-Knöpfen und Rückstand, VÖ +1 mit Statusfarbe
  (Beendet/TBA/Gestoppt/NA; neue, noch nicht gespeicherte Termine rot; VÖ +2
  und +3 im Tooltip). Der Rahmen zeigt den Status, Schilder auf dem Cover
  „bestellt“ bzw. „abholbereit“.
- **Bedienung:** Klick wählt eine Kachel aus, Doppelklick bearbeitet,
  Rechtsklick öffnet das Kontextmenü (bei buchhandel.de suchen, neue
  VÖ-Termine abfragen, Bestell-Markierung entfernen, Cover erneut suchen /
  eigenes Bild / entfernen, Bearbeiten, Löschen).
- **Menüs wie in Version 1:**
  - *Datei:* Neuer Eintrag (Strg+N), Bearbeiten, Löschen, bei buchhandel.de
    suchen (Strg+B), VÖ-Termine von buchhandel.de holen, Cover neu suchen,
    CSV importieren/exportieren, Bestellung aus E-Mail (.eml) einlesen,
    Bestellungen aus dem Postfach abrufen, von Google Drive laden
  - *Konfigurieren:* Farben (einzeln abschaltbar), Konfiguration
    (config.json), Postfach (IMAP), nach Bearbeitung zur Kachel springen,
    Gestoppt: keine Berechnung
  - *Hilfe:* LOG-Ordner öffnen, Über …
- **Werkzeugleiste:** Rückgängig (Strg+Z), Wiederholen (Strg+Y), Speichern
  (Strg+S, vorher Sicherung nach `BACKUP/`), zu Google Drive sichern,
  ISBN-Abgleich / Bestellliste, VÖ-Termine holen; Filter Verlag, VÖ +1,
  Bestellung und Typ; Sortierung nach Titel, Bänden, Gelesen, Rückstand, Typ,
  Verlag, Zugang, VÖ +1, Komplett, Beendet, **Bestellt** und **Angekommen
  (geliefert)** - auf- oder absteigend.
- **Seitenleiste:** Suche (über alle Spalten), Statistik, Anzahl nach Verlag,
  Anzahl nach Typ (Gesamt / Gelesen / Offen), Erscheinungstermine und
  ausstehende Termine, Live-Log der Sitzung.
- **Cover vom ersten Band:** werden nach dem Start im Hintergrund gesucht -
  zuerst bei der Deutschen Nationalbibliothek, als Ausweichlösung im VLB
  (buchhandel.de) und zuletzt bei manga-passion.de - und im Ordner
  `covers/` abgelegt. Jeder Titel wird nur
  einmal gesucht, ohne Treffer nach 30 Tagen erneut. „Datei → Cover neu
  suchen …“ sucht fehlende oder alle Cover noch einmal (eigene Bilder bleiben).
  Abschalten der automatischen Suche: `"cover_auto_lookup": false`.
- **Bestellungen von Konold und Thalia:** Bestätigungen, Status- und
  Abholmails (Datei oder Postfach) markieren die Titel als bestellt bzw.
  abholbereit. Beim Postfach wählt „Absender enthält“ den Buchhändler.
- **Veröffentlichungskalender** je Monat (Strg+K): eine Zeile pro
  Erscheinungstag mit den Verlagen, darunter die Titel mit Bandnummer.
- **Farbschema** hell, dunkel oder wie Windows: „Konfigurieren → Darstellung“.
- Beim Schließen mit ungespeicherten Änderungen kommt eine Rückfrage; nur ein
  Programmfenster gleichzeitig.

Anders als in Version 1: .eml-Dateien lassen sich nicht per Ziehen und
Ablegen auf das Fenster einlesen (gibt es in Flet nicht) - im Dateidialog
lassen sich aber mehrere auf einmal wählen.

## Fahrplan

1. ~~Kachelansicht mit Statusrahmen und +1-Knöpfen~~
2. ~~Cover vom ersten Band~~
3. ~~Monatlicher Veröffentlichungskalender aus VÖ +1 bis VÖ +3~~
4. ~~Übrige Funktionen aus Version 1~~
5. Release auf GitHub (exe-Build per `build.bat` gibt es schon)

## Start (Entwicklung)

Voraussetzung: Python 3.10 oder neuer.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python main.py
```

Daten (Datenbank, `config.json`, `covers/`, `LOG/`, `BACKUP/`) liegen neben `main.py`.
Wer die Sammlung aus Version 1 übernehmen will, kopiert dessen
`manga_library.db` dorthin.

Tests und Linter:

```bash
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
```

## exe bauen

```bash
build.bat
```

Legt beim ersten Mal die Build-Umgebung `.venv-build` mit den festen
Versionen aus `requirements-build.txt` an und baut mit `flet pack` die
eigenständige `dist\MangaLibraryV2.exe` (ca. 75 MB, enthält den
Flet-Programmfenster-Client). Was in die exe kommt, steht in
`build_exe.py`. Beim ersten Start entpackt die exe den Client einmalig nach
`%USERPROFILE%\.flet\client`.

`Build_work.bat` baut ebenso und kopiert die exe danach nach `..\WorkV2`
(Arbeitsordner mit den echten Daten). Die Daten dort bleiben unberührt;
eine laufende `MangaLibraryV2.exe` dort vorher beenden.

## Aufbau

- `ui/` – die Flet-Oberfläche: `app.py` Hauptfenster, `tile.py` Kachel,
  `sidebar.py` Seitenleiste, `dialogs.py`, `isbn_dialogs.py`,
  `mail_dialogs.py` Dialoge, `actions_*.py` die Aktionen (Daten, Abfragen,
  Cover), `common.py` gemeinsame Bausteine
- `gallery.py` – Status, Filter, Sortierung und Seitenleisten-Zahlen, ohne Oberfläche
- `covers.py` – Suche nach Band 1 bei der DNB, Cover-Dateien und eigene Bilder
- `library.py`, `logic.py`, `database.py`, `sorting.py`, `colors.py` … –
  Datenhaltung und Logik, aus Version 1 übernommen
- `instance_lock.py` – verhindert ein zweites Programmfenster

## Lizenz

MIT, siehe [LICENSE](LICENSE).
