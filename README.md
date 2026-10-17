# Manga Library V2

[![Tests](https://github.com/Sturmschleier/Manga-Library-V2/actions/workflows/tests.yml/badge.svg)](https://github.com/Sturmschleier/Manga-Library-V2/actions/workflows/tests.yml)

Version 2 der Manga- & Light-Novel-Bibliothek, diesmal mit einer
[Flet](https://flet.dev)-Oberfläche. Statt einer Tabelle gibt es eine
Kachelansicht mit Covern, farbigen Statusrahmen und „+1“-Knöpfen.

Version 1 (Qt/PySide6) liegt weiter im eigenen Repository
[Manga-Bibliothek](https://github.com/Sturmschleier/Manga-Bibliothek). Beide
Versionen sind komplett getrennt. Die Datenbank (`manga_library.db`) hat
dasselbe Format und lässt sich also übernehmen.

> **Stand:** frühe Entwicklungsversion. Die Kachelansicht funktioniert, die
> übrigen Funktionen aus Version 1 folgen nach und nach (siehe Fahrplan).

## Was geht schon

- **Kachelansicht** aller Titel: Cover-Fläche (vorerst Titel auf der
  Verlagsfarbe), Verlag, Typ, Besitz, Gelesen und nächster Termin
- **Farbige Rahmen** nach Status aus „VÖ +1“:
  Beendet (grün), TBA (orange), NA (pink), Gestoppt (rot), laufend (grau)
- **„+1“-Knöpfe** für Besitz und Gelesen, mit denselben Regeln wie in
  Version 1: Bei +1 Besitz rücken die VÖ-Termine nach (ohne weitere Termine
  wird es „NA“), erreichte Bestellmarkierungen entfallen. „Gelesen“ kann
  nicht über „Besitz“ steigen.
- Suche, Filter nach Typ und Status, Sortierung nach Titel, nächster VÖ,
  Zugang oder Ungelesenen
- Rückgängig/Wiederholen (Strg+Z/Strg+Y), Speichern (Strg+S) mit Sicherung
  der Datenbank nach `BACKUP/`; beim Schließen mit ungespeicherten
  Änderungen kommt eine Rückfrage
- Nur ein Programmfenster gleichzeitig

## Fahrplan

1. ~~Kachelansicht mit Statusrahmen und +1-Knöpfen~~
2. Cover vom ersten Band: ISBN von Band 1 erfassen, Bild laden und
   zwischenspeichern, eigenes Bild als Ausweichlösung
3. Monatlicher Veröffentlichungskalender aus VÖ +1 bis VÖ +3
4. Übrige Funktionen aus Version 1: Bearbeiten/Neu/Löschen, Bestellungen
   aus E-Mails, ISBN-Abgleich und Bestellliste, VÖ-Termine von
   buchhandel.de, Google-Drive-Sicherung, CSV-Import/-Export
5. exe-Build und Release

## Start (Entwicklung)

Voraussetzung: Python 3.10 oder neuer.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python main.py
```

Daten (Datenbank, `config.json`, `LOG/`, `BACKUP/`) liegen neben `main.py`.
Wer die Sammlung aus Version 1 übernehmen will, kopiert dessen
`manga_library.db` dorthin.

Tests und Linter:

```bash
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
```

## Aufbau

- `ui/` – die Flet-Oberfläche (`app.py` Hauptfenster, `tile.py` Kachel)
- `gallery.py` – Status, Filter und Sortierung der Kachelansicht, ohne Oberfläche
- `library.py`, `logic.py`, `database.py`, `sorting.py`, `colors.py` … –
  Datenhaltung und Logik, aus Version 1 übernommen
- `instance_lock.py` – verhindert ein zweites Programmfenster

## Lizenz

MIT, siehe [LICENSE](LICENSE).
