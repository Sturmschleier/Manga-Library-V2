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

Was gefunden wurde, steht in der Tabelle `covers` der Datenbank - wie
isbn_cache mit dem Titel als Schlüssel, weil die IDs beim Speichern neu
vergeben werden (siehe isbn_lookup.ensure_isbn_cache_table). Die Tabelle
ist ein Zwischenspeicher neben den eigentlichen Daten: Sie wird sofort
geschrieben, nicht erst beim "Speichern", und gehört nicht zu
Rückgängig/Wiederholen.
"""

import hashlib
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
QUELLE_EIGEN = "eigen"        # von Hand gewähltes Bild
QUELLE_KEINE = "keine"        # gesucht, nichts gefunden - nach RETRY_DAYS erneut
QUELLE_ENTFERNT = "entfernt"  # von Hand entfernt - nie wieder automatisch

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


def load_all() -> dict:
    """Alle bekannten Cover als {titel: CoverInfo}."""
    with _connect() as conn:
        rows = conn.execute("SELECT titel, isbn, datei, quelle, geprueft_am FROM covers").fetchall()
    return {r["titel"]: CoverInfo(r["titel"], r["isbn"] or "", r["datei"] or "", r["quelle"] or "",
                                  r["geprueft_am"] or "") for r in rows}


def save(info: CoverInfo) -> CoverInfo:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO covers (titel, isbn, datei, quelle, geprueft_am) VALUES (?, ?, ?, ?, ?)",
            (info.titel, info.isbn, info.datei, info.quelle, info.geprueft_am),
        )
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


def _store_image(info: CoverInfo, isbn: str, image: bytes, quelle: str) -> None:
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    (COVER_DIR / f"{isbn}.jpg").write_bytes(image)
    info.isbn, info.datei, info.quelle = isbn, f"{isbn}.jpg", quelle


def lookup_and_store(titel: str, verlag: Optional[str] = None, typ: Optional[str] = None,
                     log: Optional[list] = None, use_vlb: bool = True) -> CoverInfo:
    """Sucht ISBN und Cover von Band 1 und merkt sich das Ergebnis - auch
    ein erfolgloses, damit nicht bei jedem Start erneut gesucht wird.
    Reihenfolge siehe Moduldoku; `use_vlb=False` lässt das VLB aus."""
    isbn = find_band1_isbn(titel, verlag, typ, log) or ""
    info = CoverInfo(titel, isbn=isbn, quelle=QUELLE_KEINE, geprueft_am=_today())
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
        if only_missing and info is not None and info.quelle in (QUELLE_DNB, QUELLE_VLB) and info.path:
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
    return save(CoverInfo(titel, datei=name, quelle=QUELLE_EIGEN, geprueft_am=_today()))


def remove(titel: str) -> CoverInfo:
    """Kein Cover mehr anzeigen und auch nicht wieder automatisch suchen.
    Die Bilddatei bleibt liegen (eine DNB-Datei kann ein anderer Titel mit
    derselben ISBN nutzen)."""
    return save(CoverInfo(titel, quelle=QUELLE_ENTFERNT, geprueft_am=_today()))
