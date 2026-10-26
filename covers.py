"""
covers.py
Cover vom ersten Band für die Kachelansicht - ohne Oberfläche, damit es
sich testen lässt.

Ablauf je Titel:
  1. ISBN von Band 1 bei der DNB suchen (find_band1_isbn). Die normale
     ISBN-Suche (isbn_lookup) ist auf das aktuelle und das nächste Jahr
     beschränkt; Band 1 ist meist älter. Die DNB liefert höchstens 20
     Treffer, neueste zuerst, und kann nicht sortieren - bei langen Reihen
     wird darum rückwärts geblättert: jede weitere Anfrage nur noch mit
     Treffern vor dem ältesten Jahr der vorigen.
  2. Das Cover zu dieser ISBN vom Cover-Dienst der DNB laden und als Datei
     in COVER_DIR ablegen.
  3. Ausweichlösung VLB (buchhandel.de): Hat die DNB kein Bild, das Cover
     derselben ISBN aus dem VLB; findet die DNB keine ISBN, Band 1 im VLB
     suchen (find_band1_vlb - dort lässt sich aufsteigend sortieren, Band 1
     steht also vorn).
  4. Letzte Ausweichlösung manga-passion.de (find_manga_passion_cover): die
     passende Ausgabe (Titel, Manga oder Roman/Light Novel, möglichst
     gedruckt und vom eingetragenen Verlag) und das Cover ihres Bandes 1.

Was gefunden wurde, steht in der Tabelle `covers` der Datenbank - wie
isbn_cache mit dem Titel als Schlüssel, weil die IDs beim Speichern neu
vergeben werden (siehe isbn_lookup.ensure_isbn_cache_table). Die Tabelle
ist ein Zwischenspeicher neben den eigentlichen Daten: Sie wird sofort
geschrieben, nicht erst beim "Speichern", und gehört nicht zu
Rückgängig/Wiederholen.

Geräte-Abgleich (device_sync.py): Die Tabelle und die Bilddateien werden
mit abgeglichen. Pro Titel gilt (merge_states):
  1. von Hand Entschiedenes (eigenes Bild, entfernt, "Cover erneut suchen" /
     "Cover neu suchen") vor automatisch Gefundenem - sonst verdrängte ein
     auf dem Handy frisch gefundenes Cover ein älteres eigenes Bild vom PC,
  2. ein Ergebnis (Bild, entfernt) vor "nichts gefunden",
  3. dann die zuletzt geänderte Fassung (`geaendert`).
Bilddateien werden nur übertragen, wenn ihr Inhalt (SHA-1) abweicht.
"""

import hashlib
import os
import re
import shutil
import time
import unicodedata
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

import database as db
import isbn_lookup
import vlb_lookup
from paths import base_dir

COVER_DIR = base_dir() / "covers"
DNB_COVER_URL = "https://portal.dnb.de/opac/mvb/cover"
# Cover im VLB: -s/-m/-l = klein/mittel/groß; "l" ist etwa so groß wie das der DNB
VLB_COVER_URL = "https://buchhandel-rest.prod.kubernetes.vlb.de/cover/{isbn}/{isbn}-cover-l.jpg"
IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif")

QUELLE_DNB = "dnb"            # automatisch gefunden (DNB)
QUELLE_VLB = "vlb"            # automatisch gefunden (VLB/buchhandel.de, Ausweichlösung)
QUELLE_MP = "manga-passion"  # automatisch gefunden (manga-passion.de, letzte Ausweichlösung)
QUELLE_JNC = "jnc"            # frühere Quelle (direkt bei JNC Nina) - schon geladene Cover bleiben gültig
FOUND_SOURCES = (QUELLE_DNB, QUELLE_VLB, QUELLE_MP, QUELLE_JNC)

# manga-passion.de: Ausgaben (editions) mit Verlagen und Vorlage, je Band
# ein Cover. Vorlage (sources[].type): 0 = Manga, 1 = Roman/Light Novel.
MP_API = "https://api.manga-passion.de"
MP_HEADERS = {"User-Agent": "MangaLibrary/2 (private Bibliotheksverwaltung)", "Accept": "application/json"}
MP_SOURCE_MANGA = 0
MP_SOURCE_NOVEL = 1
QUELLE_EIGEN = "eigen"        # von Hand gewähltes Bild
QUELLE_KEINE = "keine"        # gesucht, nichts gefunden - nach RETRY_DAYS erneut
QUELLE_ENTFERNT = "entfernt"  # von Hand entfernt - nie wieder automatisch
SOURCE_LABELS = {QUELLE_DNB: "DNB", QUELLE_VLB: "VLB", QUELLE_MP: "manga-passion.de", QUELLE_JNC: "JNC Nina",
                 QUELLE_EIGEN: "eigenes Bild"}

RETRY_DAYS = 30
MAX_QUERIES_PER_PASS = 15     # Anfragen je Durchgang (mit/ohne Verlag) beim Rückwärtsblättern
DNB_PAGE_SIZE = 20

# Nur sichere Zuordnungen: "titeltext" greift bei Band 1 zu oft daneben
# (z.B. "One Piece - Heroines 1" statt One Piece Band 1)
_ACCEPTED_CONFIDENCE = ("band+verlag", "band_only")


@dataclass
class CoverInfo:
    titel: str
    isbn: str = ""
    datei: str = ""         # Dateiname in COVER_DIR, leer = kein Bild
    quelle: str = QUELLE_KEINE
    geprueft_am: str = ""   # ISO-Datum der letzten Suche/Änderung
    geaendert: str = ""     # Zeitpunkt der letzten Änderung (UTC, database.now_stamp) - für den Abgleich
    manuell: bool = False   # von Hand entschieden (eigenes Bild, entfernt, gezielt gesucht)

    @property
    def path(self) -> Optional[Path]:
        """Pfad der Bilddatei, sofern es sie (noch) gibt."""
        if not self.datei:
            return None
        path = COVER_DIR / self.datei
        return path if path.is_file() else None


# ----------------------------------------------------------------- Tabelle

@contextmanager
def _connect():
    """Verbindung, die am Ende festschreibt und geschlossen wird."""
    with closing(db.get_connection()) as conn, conn:
        yield conn


COLUMNS = ("titel", "isbn", "datei", "quelle", "geprueft_am", "geaendert", "manuell")
MANUAL_SOURCES = (QUELLE_EIGEN, QUELLE_ENTFERNT)


def ensure_table() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS covers (
                titel TEXT PRIMARY KEY,
                isbn TEXT,
                datei TEXT,
                quelle TEXT,
                geprueft_am TEXT
            )
            """
        )
        # für den Geräte-Abgleich ergänzt; eigene und entfernte Cover waren
        # schon immer von Hand entschieden
        existing = {row[1] for row in conn.execute("PRAGMA table_info(covers)").fetchall()}
        if "geaendert" not in existing:
            conn.execute("ALTER TABLE covers ADD COLUMN geaendert TEXT")
        if "manuell" not in existing:
            conn.execute("ALTER TABLE covers ADD COLUMN manuell INTEGER")
            conn.execute("UPDATE covers SET manuell = 1 WHERE quelle IN (?, ?)", MANUAL_SOURCES)


def _info(row) -> CoverInfo:
    return CoverInfo(row["titel"], row["isbn"] or "", row["datei"] or "", row["quelle"] or "",
                     row["geprueft_am"] or "", row["geaendert"] or "", bool(row["manuell"]))


def load_all() -> dict:
    """Alle bekannten Cover als {titel: CoverInfo}."""
    with _connect() as conn:
        rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM covers").fetchall()
    return {r["titel"]: _info(r) for r in rows}


def _write(conn, info: CoverInfo) -> None:
    conn.execute(
        f"INSERT OR REPLACE INTO covers ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})",
        (info.titel, info.isbn, info.datei, info.quelle, info.geprueft_am, info.geaendert, int(info.manuell)),
    )


def save(info: CoverInfo) -> CoverInfo:
    """Speichert `info` mit der aktuellen Änderungszeit."""
    info.geaendert = db.now_stamp()
    with _connect() as conn:
        _write(conn, info)
    return info


def forget(titel: str) -> None:
    """Vergisst den Eintrag - der Titel wird dann wieder automatisch gesucht."""
    with _connect() as conn:
        conn.execute("DELETE FROM covers WHERE titel = ?", (titel,))


def _today() -> str:
    return datetime.now().date().isoformat()


def needs_lookup(info: Optional[CoverInfo], today: Optional[str] = None) -> bool:
    """Soll für diesen Titel automatisch gesucht werden? Ja, wenn noch nie
    gesucht wurde oder die letzte erfolglose Suche über RETRY_DAYS her ist
    (Band 1 einer neuen Reihe ist bei der DNB oft erst kurz vor dem
    Erscheinen erfasst). Gefundene, eigene und entfernte Cover nie."""
    if info is None:
        return True
    if info.quelle != QUELLE_KEINE:
        return False   # gefunden (DNB/VLB), eigenes Bild oder entfernt
    try:
        last = datetime.fromisoformat(info.geprueft_am).date()
    except ValueError:
        return True
    now = datetime.fromisoformat(today).date() if today else datetime.now().date()
    return now - last >= timedelta(days=RETRY_DAYS)


def pending(entries, infos: dict, today: Optional[str] = None) -> list:
    """Einträge, für die automatisch ein Cover gesucht werden soll (nur mit
    Titel, jeder Titel einmal)."""
    seen = set()
    result = []
    for entry in entries:
        titel = (entry.get("titel") or "").strip()
        if titel and titel not in seen and needs_lookup(infos.get(titel), today):
            seen.add(titel)
            result.append(entry)
    return result


# ------------------------------------------------------------ DNB-Suche

# Zusatz am Ende des eigenen Titels, den die DNB nicht im Reihentitel führt:
# "Accel World – Light Novel", "Overlord (Manga)"
_TYPE_SUFFIX_RE = re.compile(r"[\s\-–(]*\b(light novel|novel|manga|manhwa)\)?\s*$", re.IGNORECASE)

# Felder mit dem Reihentitel: 245 $a (Titel), 490 $a (Gesamttitel),
# 800/810/811 $t und 830 $a (Gesamttitel-Ansetzung)
_SERIES_FIELDS = (("245", "a"), ("490", "a"), ("800", "t"), ("810", "t"), ("811", "t"), ("830", "a"))
_NON_SORT_CHARS = str.maketrans("", "", "\x98\x9c")


def search_title(titel: str) -> str:
    """Der eigene Titel ohne Typ-Zusatz am Ende (siehe _TYPE_SUFFIX_RE)."""
    stripped = _TYPE_SUFFIX_RE.sub("", titel or "").strip()
    return stripped or (titel or "").strip()


def _normalize(text: str) -> str:
    """Kleingeschrieben, nur Wörter. NFKC, weil die DNB Umlaute zerlegt
    liefert ("a" + Trema statt "ä")."""
    text = unicodedata.normalize("NFKC", (text or "").translate(_NON_SORT_CHARS))
    return " ".join(re.findall(r"\w+", text.casefold()))


# Trennt einen Untertitel ab: "Arifureta - der Kampf zurück in meine Welt",
# "Overlord: Das Buch" (nicht aber "One piece party")
_SUBTITLE_SEP_RE = re.compile(r"\s+[-–]\s+|\s*:\s+")

SERIES_EXACT = 2      # Reihentitel entspricht genau dem gesuchten Titel
SERIES_SUBTITLE = 1   # gesuchter Titel + Untertitel ("Arifureta - der Kampf ...")
SERIES_NONE = 0


def series_match(record, titel: str) -> int:
    """Gehört der Record zur Reihe selbst? SERIES_EXACT, SERIES_SUBTITLE
    oder SERIES_NONE - "One piece party 1" ist nicht Band 1 von "One Piece"."""
    wanted = _normalize(search_title(titel))
    best = SERIES_NONE
    for tag, code in _SERIES_FIELDS:
        for df in isbn_lookup._extract_datafields(record, tag):
            raw = unicodedata.normalize("NFKC", (isbn_lookup._subfield(df, code) or "").translate(_NON_SORT_CHARS))
            if _normalize(raw) == wanted:
                return SERIES_EXACT
            if _normalize(_SUBTITLE_SEP_RE.split(raw, maxsplit=1)[0]) == wanted:
                best = SERIES_SUBTITLE
    return best


def series_matches(record, titel: str) -> bool:
    """Reihentitel genau gleich (siehe series_match)."""
    return series_match(record, titel) == SERIES_EXACT


def find_band1_isbn(titel: str, verlag: Optional[str] = None, typ: Optional[str] = None,
                     log: Optional[list] = None) -> Optional[str]:
    """ISBN der normalen Ausgabe von Band 1, sonst None (siehe Moduldoku).
    Erst mit Verlag eingeschränkt, dann ohne. Nur Records der Reihe selbst
    zählen (series_match), keine Ableger mit eigener Bandzählung.

    Ein genau passender Reihentitel gewinnt sofort. Einer mit Untertitel
    ("Arifureta - der Kampf ...") ist nur die Ausweichlösung, falls es keinen
    genauen gibt - dann der älteste gefundene, denn Ableger mit Untertitel
    ("One Piece - Heroines") erscheinen meist nach der Hauptreihe."""
    titel = search_title(titel)
    base = f"{isbn_lookup._cql_title(titel)} and mat=books"
    passes = []
    verlag_term = isbn_lookup._verlag_search_term(verlag)
    if verlag_term:
        passes.append((f"{base} and vlg={isbn_lookup._cql_term(verlag_term)}", "Band 1 mit Verlag"))
    passes.append((base, "Band 1 ohne Verlag" if verlag_term else "Band 1"))

    first_request = True
    fallback = None
    for query, label in passes:
        before = None
        series_seen = False
        for _ in range(MAX_QUERIES_PER_PASS):
            if not first_request:
                time.sleep(isbn_lookup.REQUEST_DELAY_SECONDS)   # freundlich zur DNB
            first_request = False
            paged = query if before is None else f"{query} and jhr<{before}"
            records = isbn_lookup.fetch_dnb_records(paged, label, log)
            if not records:
                break
            levels = [(r, series_match(r, titel)) for r in records]
            exact = [r for r, level in levels if level == SERIES_EXACT]
            subtitled = [r for r, level in levels if level == SERIES_SUBTITLE]
            series_seen = series_seen or bool(exact or subtitled)
            isbn, confidence, _specials = isbn_lookup.match_dnb_records(exact, label, titel, 1, verlag, typ, log)
            if isbn and confidence in _ACCEPTED_CONFIDENCE:
                return isbn
            isbn, confidence, _specials = isbn_lookup.match_dnb_records(
                subtitled, label + ", mit Untertitel", titel, 1, verlag, typ, log)
            if isbn and confidence in _ACCEPTED_CONFIDENCE:
                fallback = isbn   # ältere Seiten überschreiben: der älteste zählt
            if len(records) < DNB_PAGE_SIZE:
                break   # alles gesehen
            before = _next_year_bound(records, before)
            if before is None:
                break   # ohne Jahresangaben kommt das Blättern nicht weiter
        if series_seen:
            break   # die Reihe gibt es beim eingetragenen Verlag - ohne Verlag wäre nur Rauschen dabei
    return fallback


def _next_year_bound(records, before: Optional[int]) -> Optional[int]:
    """Obergrenze (jhr<...) für die nächste, ältere Seite: das älteste Jahr
    der Seite. Das Jahr im Datensatz kann vom Suchindex der DNB abweichen;
    damit es trotzdem vorangeht, mindestens ein Jahr vor der bisherigen
    Grenze."""
    years = [y for y in (isbn_lookup.record_year(r) for r in records) if y]
    if not years:
        return before - 1 if before is not None else None
    oldest = min(years)
    return min(oldest, before - 1) if before is not None else oldest


def _download_image(url: str, params: Optional[dict] = None) -> Optional[bytes]:
    """Bilddaten von `url`, oder None (kein Bild - DNB und VLB antworten
    dann mit 404 - oder Netzwerkfehler)."""
    try:
        resp = requests.get(url, params=params, timeout=20)
    except requests.RequestException:
        return None
    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200 or not content_type.startswith("image/") or len(resp.content) < 1000:
        return None
    return resp.content


def download_cover(isbn: str) -> Optional[bytes]:
    """Cover zur ISBN vom Cover-Dienst der DNB, oder None."""
    return _download_image(DNB_COVER_URL, {"isbn": isbn})


def download_vlb_cover(isbn: str) -> Optional[bytes]:
    """Cover zur ISBN aus dem VLB (buchhandel.de), oder None."""
    return _download_image(VLB_COVER_URL.format(isbn=isbn))


def _vlb_query(titel: str) -> str:
    """Suche im VLB ohne Jahresgrenze (Band 1 ist meist älter)."""
    titel = " ".join(vlb_lookup._QUERY_UNSAFE_RE.sub(" ", titel).split())
    return f"(ti={titel}) und pt=pbook"


def find_band1_vlb(titel: str, verlag: Optional[str] = None, typ: Optional[str] = None) -> Optional[str]:
    """ISBN von Band 1 im VLB, sonst None. Die Zuordnung der Treffer zur Reihe
    (Verlag, Titelstamm, Manga/Light Novel, keine Sonderausgaben) übernimmt
    vlb_lookup.find_next_volumes - dieselbe Logik wie beim Abgleich der
    VÖ-Termine. Ohne Treffer wird noch der Titel ohne Untertitel versucht."""
    entry = {"titel": titel, "verlag": verlag or "", "typ": typ or "", "baende_bis": "0"}
    is_ln = (typ or "").strip().lower() == "light novel"
    names = [vlb_lookup._strip_light_novel(titel) or titel if is_ln else search_title(titel)]
    short = vlb_lookup._TITLE_SPLIT_RE.split(names[0])[0].strip()
    if short and short != names[0]:
        names.append(short)
    for i, name in enumerate(names):
        if i:
            time.sleep(vlb_lookup.REQUEST_DELAY_SECONDS)   # Fair Use, siehe vlb_lookup
        try:
            products = vlb_lookup.fetch_products(_vlb_query(name), newest_first=False)
        except vlb_lookup.VlbError:
            return None
        volumes, _note = vlb_lookup.find_next_volumes(entry, products)
        if 1 in volumes and volumes[1].isbn:
            return volumes[1].isbn
    return None


# ------------------------------------------------------- manga-passion.de

# Zusätze im Titel einer Ausgabe, die nicht zum Reihentitel gehören
_MP_SUFFIX_RE = re.compile(
    r"(\s*\([^)]*\))+\s*$|\s*[–-]\s*(light novel|taschenbuchausgabe)\s*$|\s+roman\s*$", re.IGNORECASE)


def mp_edition_title(title: str) -> str:
    """ "Solo Leveling Roman – Taschenbuchausgabe (eBook)" -> "Solo Leveling" """
    previous = None
    title = title or ""
    while previous != title:   # Zusätze können aufeinander folgen
        previous, title = title, _MP_SUFFIX_RE.sub("", title).strip()
    return title


def _mp_rank(edition: dict, titel: str, verlag: Optional[str], typ: Optional[str]) -> Optional[tuple]:
    """Rangfolge einer Ausgabe (kleiner = besser), None wenn der Titel nicht
    passt. Vorrang hat die Vorlage passend zum Typ (Manga oder Roman/Light
    Novel) - "Solo Leveling Light Novel" bekommt so den Roman, nicht den
    Manhwa. Gibt es nur Ausgaben mit anderer Vorlage, zählt auch eine davon
    (manga-passion ordnet manches anders ein, z.B. Sachbücher). Danach
    gedruckt vor eBook, eingetragener Verlag vor anderen."""
    if _normalize(mp_edition_title(edition.get("title") or "")) != _normalize(search_title(titel)):
        return None
    wanted = MP_SOURCE_NOVEL if (typ or "").strip().casefold() == "light novel" else MP_SOURCE_MANGA
    source_types = {s.get("type") for s in edition.get("sources") or []}
    type_ok = not source_types or wanted in source_types
    publisher_names = " ".join(p.get("name") or "" for p in edition.get("publishers") or [])
    verlag_ok = bool(isbn_lookup._normalize_verlag(verlag or "") & isbn_lookup._normalize_verlag(publisher_names))
    return (0 if type_ok else 1, 0 if edition.get("print") else 1, 0 if verlag_ok else 1)


def find_manga_passion_cover(titel: str, verlag: Optional[str] = None, typ: Optional[str] = None) -> Optional[str]:
    """URL des Covers von Band 1 bei manga-passion.de, sonst None."""
    try:
        resp = requests.get(f"{MP_API}/editions", params={"search": search_title(titel)},
                            headers=MP_HEADERS, timeout=20)
        resp.raise_for_status()
        ranked = sorted(
            (rank, i, e) for i, e in enumerate(resp.json() or [])
            if (rank := _mp_rank(e, titel, verlag, typ)) is not None
        )
        if not ranked:
            return None
        edition = ranked[0][2]
        resp = requests.get(f"{MP_API}/editions/{edition['id']}/volumes", headers=MP_HEADERS, timeout=20)
        resp.raise_for_status()
        volumes = resp.json() or []
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    first = next((v for v in volumes if v.get("number") == 1 and v.get("cover")), None)
    return (first or {}).get("cover") or edition.get("cover") or None


def _store_image(info: CoverInfo, isbn: str, image: bytes, quelle: str) -> None:
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    (COVER_DIR / f"{isbn}.jpg").write_bytes(image)
    info.isbn, info.datei, info.quelle = isbn, f"{isbn}.jpg", quelle


def lookup_and_store(titel: str, verlag: Optional[str] = None, typ: Optional[str] = None,
                     log: Optional[list] = None, use_vlb: bool = True, manuell: bool = False) -> CoverInfo:
    """Sucht ISBN und Cover von Band 1 und merkt sich das Ergebnis - auch
    ein erfolgloses, damit nicht bei jedem Start erneut gesucht wird.
    Reihenfolge siehe Moduldoku; `use_vlb=False` lässt das VLB aus.
    `manuell`: von Hand angestoßen (zählt beim Geräte-Abgleich wie ein
    eigenes Bild, siehe Moduldoku)."""
    isbn = find_band1_isbn(titel, verlag, typ, log) or ""
    info = CoverInfo(titel, isbn=isbn, quelle=QUELLE_KEINE, geprueft_am=_today(), manuell=manuell)
    image = download_cover(isbn) if isbn else None
    if image:
        _store_image(info, isbn, image, QUELLE_DNB)
        return save(info)
    if use_vlb:
        image = download_vlb_cover(isbn) if isbn else None
        if not image and not isbn:
            vlb_isbn = find_band1_vlb(titel, verlag, typ)
            if vlb_isbn:
                isbn = info.isbn = vlb_isbn
                image = download_vlb_cover(vlb_isbn)
        if image:
            _store_image(info, isbn, image, QUELLE_VLB)
            return save(info)
    url = find_manga_passion_cover(titel, verlag, typ)
    image = _download_image(url) if url else None
    if image:
        name = "mp_" + hashlib.sha1(titel.encode("utf-8")).hexdigest()[:12]
        COVER_DIR.mkdir(parents=True, exist_ok=True)
        (COVER_DIR / f"{name}.jpg").write_bytes(image)
        info.datei, info.quelle = f"{name}.jpg", QUELLE_MP
    return save(info)


def refresh_targets(entries, infos: dict, only_missing: bool = True) -> list:
    """Einträge für "Cover neu suchen": nur die ohne Bild (auch erfolglos
    gesuchte und entfernte), oder alle - eigene Bilder bleiben immer
    unangetastet. Jeder Titel einmal."""
    seen = set()
    result = []
    for entry in entries:
        titel = (entry.get("titel") or "").strip()
        if not titel or titel in seen:
            continue
        info = infos.get(titel)
        if info is not None and info.quelle == QUELLE_EIGEN:
            continue
        if only_missing and info is not None and info.quelle in FOUND_SOURCES and info.path:
            continue
        seen.add(titel)
        result.append(entry)
    return result


def set_custom(titel: str, source: Path) -> CoverInfo:
    """Übernimmt ein eigenes Bild als Cover (Kopie in COVER_DIR)."""
    source = Path(source)
    ext = source.suffix.lower().lstrip(".")
    if ext not in IMAGE_EXTENSIONS:
        raise ValueError(f"„{source.name}“ ist kein unterstütztes Bild ({', '.join(IMAGE_EXTENSIONS)}).")
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    name = f"eigen_{hashlib.sha1(titel.encode('utf-8')).hexdigest()[:12]}.{ext}"
    for old in COVER_DIR.glob(f"{Path(name).stem}.*"):
        old.unlink()   # ein früher gewähltes Bild mit anderer Endung
    shutil.copyfile(source, COVER_DIR / name)
    return save(CoverInfo(titel, datei=name, quelle=QUELLE_EIGEN, geprueft_am=_today(), manuell=True))


def remove(titel: str) -> CoverInfo:
    """Kein Cover mehr anzeigen und auch nicht wieder automatisch suchen.
    Die Bilddatei bleibt liegen (eine DNB-Datei kann ein anderer Titel mit
    derselben ISBN nutzen)."""
    return save(CoverInfo(titel, quelle=QUELLE_ENTFERNT, geprueft_am=_today(), manuell=True))


# ------------------------------------------------------- Geräte-Abgleich

# Dateinamen, die beim Abgleich angenommen werden: nur ein Name (kein Pfad)
# mit Bild-Endung - wie ihn _store_image, lookup_and_store und set_custom anlegen
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def safe_file_name(name) -> bool:
    return (isinstance(name, str) and bool(_SAFE_NAME_RE.match(name)) and not name.startswith(".")
            and name.rsplit(".", 1)[-1].lower() in IMAGE_EXTENSIONS)


def file_hash(datei: str) -> str:
    """SHA-1 der Bilddatei in COVER_DIR, leer wenn es sie nicht gibt."""
    if not safe_file_name(datei):
        return ""
    try:
        return hashlib.sha1((COVER_DIR / datei).read_bytes()).hexdigest()
    except OSError:
        return ""


def file_hashes() -> dict:
    """{Dateiname: SHA-1} aller Bilddateien in COVER_DIR."""
    try:
        names = [p.name for p in COVER_DIR.iterdir() if p.is_file()]
    except OSError:
        return {}
    return {name: h for name in names if (h := file_hash(name))}


def sync_state() -> list:
    """Alle Cover-Einträge für den Abgleich, je mit dem SHA-1 der eigenen
    Bilddatei ("sha", leer wenn sie fehlt)."""
    ensure_table()
    hashes = file_hashes()
    return [dict(_record(info), sha=hashes.get(info.datei, "")) for info in load_all().values()]


def _record(info: CoverInfo) -> dict:
    return {"titel": info.titel, "isbn": info.isbn, "datei": info.datei, "quelle": info.quelle,
            "geprueft_am": info.geprueft_am, "geaendert": info.geaendert, "manuell": info.manuell}


def _clean_record(raw) -> Optional[dict]:
    """Nur gültige Einträge eines anderen Geräts; None sonst."""
    if not isinstance(raw, dict) or not isinstance(raw.get("titel"), str) or not raw["titel"]:
        return None
    rec = {k: raw.get(k) if isinstance(raw.get(k), str) else "" for k in
           ("titel", "isbn", "datei", "quelle", "geprueft_am", "geaendert", "sha")}
    rec["manuell"] = bool(raw.get("manuell"))
    if rec["datei"] and not safe_file_name(rec["datei"]):
        return None
    if rec["sha"] and not re.fullmatch(r"[0-9a-f]{40}", rec["sha"]):
        rec["sha"] = ""
    return rec


def _rank(rec: dict) -> tuple:
    """Größer = gewinnt (siehe Moduldoku); bei Gleichstand fest nach Inhalt,
    damit beide Geräte dieselbe Fassung wählen - eine mit Bilddatei vor
    derselben ohne."""
    return (rec["manuell"], rec["quelle"] != QUELLE_KEINE, rec["geaendert"], rec["datei"], rec["quelle"],
            rec["isbn"], rec["geprueft_am"], rec["sha"])


def merge_states(local: list, remote: list) -> tuple[dict, list]:
    """Führt zwei Cover-Stände zusammen (Regeln siehe Moduldoku). Gibt
    ({titel: Gewinner samt "sha" der gewünschten Bilddatei}, [Titel, deren
    Eintrag sich gegenüber `local` ändert]) zurück."""
    local_by_title = {r["titel"]: r for r in map(_clean_record, local) if r}
    merged = dict(local_by_title)
    for rec in filter(None, map(_clean_record, remote)):
        current = merged.get(rec["titel"])
        if current is None or _rank(rec) > _rank(current):
            merged[rec["titel"]] = rec
    fields = ("isbn", "datei", "quelle", "geprueft_am", "geaendert", "manuell")
    changed = [t for t, rec in merged.items()
               if t not in local_by_title or any(rec[f] != local_by_title[t][f] for f in fields)]
    return merged, changed


def merge_sync(remote: list) -> tuple[dict, list]:
    """Führt den Cover-Stand eines anderen Geräts mit dem eigenen zusammen
    und speichert die geänderten Einträge (mit deren Änderungszeit). Gibt
    die Rückgabe von merge_states zurück."""
    merged, changed = merge_states(sync_state(), remote)
    if changed:
        with _connect() as conn:
            for titel in changed:
                rec = merged[titel]
                _write(conn, CoverInfo(titel, rec["isbn"], rec["datei"], rec["quelle"], rec["geprueft_am"],
                                       rec["geaendert"], rec["manuell"]))
    return merged, changed


def wanted_files(merged: dict) -> dict:
    """Bilddateien, die hier fehlen oder anders aussehen als beim Gewinner:
    {Dateiname: gewünschter SHA-1}."""
    hashes = file_hashes()
    return {rec["datei"]: rec["sha"] for rec in merged.values()
            if rec["datei"] and rec["sha"] and hashes.get(rec["datei"]) != rec["sha"]}


def read_file(datei: str) -> bytes:
    if not safe_file_name(datei):
        raise ValueError(f"Ungültiger Dateiname: {datei!r}")
    return (COVER_DIR / datei).read_bytes()


def store_file(datei: str, data: bytes, sha: str) -> None:
    """Legt eine empfangene Bilddatei ab - nur mit gültigem Namen und wenn
    der Inhalt zum erwarteten SHA-1 passt."""
    if not safe_file_name(datei):
        raise ValueError(f"Ungültiger Dateiname: {datei!r}")
    if hashlib.sha1(data).hexdigest() != sha:
        raise ValueError(f"Inhalt von {datei} passt nicht zur Prüfsumme")
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = COVER_DIR / f".{datei}.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, COVER_DIR / datei)
