# Manga Library V2

[![Tests](https://github.com/Sturmschleier/Manga-Library-V2/actions/workflows/tests.yml/badge.svg)](https://github.com/Sturmschleier/Manga-Library-V2/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/Sturmschleier/Manga-Library-V2)](https://github.com/Sturmschleier/Manga-Library-V2/releases/latest)

Version 2 der Manga- & Light-Novel-Bibliothek, diesmal mit einer
[Flet](https://flet.dev)-Oberfläche. Statt einer Tabelle gibt es eine
Kachelansicht mit Covern, farbigen Statusrahmen und „+1“-Knöpfen.

Version 1 (Qt/PySide6) liegt weiter im eigenen Repository
[Manga-Bibliothek](https://github.com/Sturmschleier/Manga-Bibliothek). Beide
Versionen sind komplett getrennt. Die Datenbank (`manga_library.db`) hat
dasselbe Format und lässt sich also übernehmen.

## Herunterladen und starten

1. Unter [Releases](https://github.com/Sturmschleier/Manga-Library-V2/releases/latest)
   `MangaLibraryV2.exe` herunterladen (Windows, kein Python nötig).
2. In einen eigenen Ordner legen und starten. Die exe legt ihre Daten neben
   sich ab: `manga_library.db`, `config.json`, `covers/`, `LOG/`, `BACKUP/`.
   Für Google Drive gehört `credentials.json` ebenfalls in diesen Ordner.
3. Wer die Sammlung aus Version 1 übernehmen will, kopiert deren
   `manga_library.db` (und gern `config.json`) in den Ordner.

Beim allerersten Start entpackt die exe das Programmfenster einmalig nach
`%USERPROFILE%\.flet\client` - das dauert ein paar Sekunden. Die exe ist
nicht signiert; Windows SmartScreen kann deshalb beim ersten Start warnen
(„Weitere Informationen → Trotzdem ausführen“). Prüfsumme und
Herkunftsnachweis siehe Release-Seite.

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

Das Icon der exe und des Programmfensters ist `assets/MangaLibraryV2.ico`.
Es wird von `assets/make_icon.py` gezeichnet (braucht Pillow) – zum Ändern
dort anpassen und `python assets/make_icon.py` ausführen.

`Build_work.bat` baut ebenso und kopiert die exe danach nach `..\WorkV2`
(Arbeitsordner mit den echten Daten). Die Daten dort bleiben unberührt;
eine laufende `MangaLibraryV2.exe` dort vorher beenden.

## Android-App (APK) bauen

```bash
build_apk.bat
```

Baut `dist\MangaLibraryV2.apk` mit `flet build apk` in derselben Build-Umgebung
`.venv-build` wie die exe. Voraussetzung ist der **Windows-Entwicklermodus**
(Einstellungen → System → Für Entwickler). Beim ersten Lauf lädt Flet Flutter,
JDK 17 und das Android SDK (mehrere GB) nach `E:\Claude\.android-build` – denselben
Ordner wie die Anime-Liste, nicht nach C:. Ein anderer Ort: Umgebungsvariable
`MANGALIB_ANDROID_TOOLS`.

Gebaut wird aus dem Zwischenordner `.apk-src`, den `build_apk.py` nur mit dem
Programmcode, dem Icon und `pyproject.toml` füllt – Datenbank, `config.json`,
Cover und Google-Zugangsdaten landen also nicht in der APK. App-Name,
Paketliste und Berechtigungen stehen in `pyproject.toml` (`[project]`,
`[tool.flet]`), die Versionsnummer kommt aus `appinfo.VERSION`.

Auf dem Handy:
- eigene Datenbank im privaten App-Ordner; die Sammlung kommt per
  **Geräte-Abgleich** (siehe unten) aufs Handy
- kompakte Oberfläche: Symbolleiste mit Menü (☰), Suche, wischbare Filterzeile,
  Statistik/Termine/Legende unter „Übersicht“, **langes Drücken** auf eine Kachel
  statt Rechtsklick
- beim Wechsel in den Hintergrund wird automatisch gespeichert
- nicht verfügbar: Google Drive (Anmeldung braucht einen Browser auf demselben
  Gerät), Postfach-Passwort speichern, LOG-Ordner öffnen

Zum Ausprobieren der Handy-Oberfläche am PC: `set MANGALIB_MOBILE=1` vor
`python main.py`.

## Geräte-Abgleich (WLAN)

Gleicht die Sammlung zwischen beliebigen Geräten im selben WLAN ab (PC, Handy,
Tablet) – wie bei der Anime-Liste:

1. Auf **beiden** Geräten „Geräte-Abgleich“ öffnen (PC: Werkzeugleiste oder
   *Datei*; Handy: Sync-Symbol) – nur solange das Fenster offen ist, ist ein
   Gerät empfangsbereit.
2. Beim ersten Mal auf einem Gerät „Kopplungscode anzeigen“, auf dem anderen
   „Im WLAN suchen“ → „Koppeln“ und den Code eingeben (oder die angezeigte
   IP-Adresse unter „Verbinden“ eintragen).
3. Danach genügt „Abgleichen“ beim gekoppelten Gerät.

Abgeglichen wird der gespeicherte Stand (ungespeicherte Änderungen werden
vorher gespeichert). Pro Eintrag gilt die zuletzt gespeicherte Fassung,
Löschungen werden übertragen, Einträge mit gleichem Titel zusammengelegt. Vor
jeder Änderung sichert die Bibliothek die Datenbank nach `BACKUP/…_vor-sync.db`.
Einstellungen (`config.json`), eigene Cover und Passwörter bleiben auf dem
Gerät; fehlende Cover werden nach dem Abgleich gesucht. Kopplungen stehen in
`sync_geraete.json` neben der Datenbank. Nach dem Koppeln sind alle Anfragen
signiert (HMAC), andere Geräte im WLAN werden abgewiesen. Am PC fragt die
Windows-Firewall beim ersten Öffnen, ob der Zugriff im privaten Netzwerk erlaubt
werden soll – das muss erlaubt werden (Port 47812).

## Neue Version veröffentlichen

Die exe für ein Release baut **GitHub** (Workflow `.github/workflows/release.yml`)
auf einem frischen Windows-Rechner mit denselben festen Versionen wie
`build.bat`:

1. `VERSION` in `appinfo.py` per Pull Request anheben (angezeigt unter
   „Hilfe → Über …“), optional den Text in `docs/release-notes/v<VERSION>.md`
   schreiben, mergen.
2. Tag setzen und hochladen, z. B. `git tag v2.0.1 && git push origin v2.0.1`.
3. Der Workflow prüft, dass der Tag zu `VERSION` passt und auf `main` liegt,
   baut `MangaLibraryV2.exe`, berechnet die Prüfsumme, erstellt den
   Herkunftsnachweis und legt das Release mit beiden Dateien an.

Zum Ausprobieren ohne Release: Reiter **Actions → Release → Run workflow**; die
exe steht dann als Artefakt am Durchlauf.

**Herkunft prüfen:** `gh attestation verify MangaLibraryV2.exe --repo Sturmschleier/Manga-Library-V2`

## Aufbau

- `ui/` – die Flet-Oberfläche: `app.py` Hauptfenster, `tile.py` Kachel,
  `sidebar.py` Seitenleiste, `dialogs.py`, `isbn_dialogs.py`,
  `mail_dialogs.py`, `calendar_dialog.py` Dialoge, `actions_*.py` die
  Aktionen (Daten, Abfragen, Cover), `theme.py` Farbschema, `common.py`
  gemeinsame Bausteine
- `gallery.py` – Status, Filter, Sortierung und Seitenleisten-Zahlen, ohne Oberfläche
- `covers.py` – Cover von Band 1 (DNB, VLB, manga-passion.de), Cover-Dateien und eigene Bilder
- `release_calendar.py` – Termine eines Monats für den Veröffentlichungskalender
- `order_mail.py`, `mail_fetch.py` – Bestellmails von Konold und Thalia (Datei und Postfach)
- `library.py`, `logic.py`, `database.py`, `sorting.py`, `colors.py` … –
  Datenhaltung und Logik, aus Version 1 übernommen
- `instance_lock.py` – verhindert ein zweites Programmfenster
- `device_sync.py`, `sync_merge.py`, `ui/sync_dialog.py` – Geräte-Abgleich im WLAN
  (Netzwerk, Zusammenführungsregeln, Fenster)
- `build.bat`, `build_exe.py`, `requirements-build.txt` – exe-Build;
  `build_apk.bat`, `build_apk.py` – Android-Build; `assets/` – Programm-Icon; `.github/workflows/` – Tests und Release

## Lizenz

MIT, siehe [LICENSE](LICENSE).
