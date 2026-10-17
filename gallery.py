"""
gallery.py
Logik der Kachelansicht ohne Flet: Status eines Werks (für die farbigen
Rahmen), Filtern und Sortieren der Kacheln. Bewusst ohne Oberfläche, damit
sie sich direkt testen lässt - ui/ ruft nur diese Funktionen auf.

Der Status steht wie in Version 1 in der Spalte "VÖ +1" (voe_1): "Beendet",
"TBA", "NA" oder "Gestoppt". Alles andere (ein Datum, "Fortlaufend",
Freitext wie "Band 17 11.06.2025") gilt als laufende Reihe.
"""

import sorting
from logic import parse_int

STATUS_LAUFEND = "laufend"
STATUS_BEENDET = "beendet"
STATUS_TBA = "tba"
STATUS_NA = "na"
STATUS_GESTOPPT = "gestoppt"

# Reihenfolge = Reihenfolge in Filter und Legende
STATUS_LABELS = {
    STATUS_LAUFEND: "Laufend",
    STATUS_BEENDET: "Beendet",
    STATUS_TBA: "TBA",
    STATUS_NA: "NA",
    STATUS_GESTOPPT: "Gestoppt",
}

# Kräftige Rahmenfarben - dieselben Farbtöne wie die hellen Zellfarben aus
# colors.VOE1_STATUS_COLORS, aber satt genug, um als schmaler Rahmen
# aufzufallen. Laufende Reihen bekommen einen neutralen grauen Rahmen.
STATUS_BORDER_COLORS = {
    STATUS_LAUFEND: "#B0B7C3",
    STATUS_BEENDET: "#2E9E3F",
    STATUS_TBA: "#F08C00",
    STATUS_NA: "#D63AAF",
    STATUS_GESTOPPT: "#D93030",
}

FILTER_ALL = "Alle"

SORT_TITEL = "Titel"
SORT_VOE = "Nächste VÖ"
SORT_ZUGANG = "Zugang (neueste zuerst)"
SORT_OFFEN = "Ungelesen (meiste zuerst)"
SORT_OPTIONS = (SORT_TITEL, SORT_VOE, SORT_ZUGANG, SORT_OFFEN)


def status_of(entry: dict) -> str:
    """Status eines Werks aus "VÖ +1" (siehe Moduldoku)."""
    value = (entry.get("voe_1") or "").strip().lower()
    if value in (STATUS_BEENDET, STATUS_TBA, STATUS_NA, STATUS_GESTOPPT):
        return value
    return STATUS_LAUFEND


def next_release(entry: dict) -> str:
    """Der nächste Termin für die Kachel: "VÖ +1", sofern es kein Status
    ist (der steckt schon im Rahmen), sonst leer."""
    if status_of(entry) != STATUS_LAUFEND:
        return ""
    return (entry.get("voe_1") or "").strip()


def unread_count(entry: dict) -> int:
    """Gekaufte, aber noch nicht gelesene Bände (nie negativ). Nicht lesbare
    Werte zählen als 0."""
    owned = parse_int(entry.get("baende_bis")) or 0
    read = parse_int(entry.get("gelesen_bis")) or 0
    return max(owned - read, 0)


def matches(entry: dict, search: str = "", typ: str = FILTER_ALL, status: str = FILTER_ALL) -> bool:
    """Filter der Werkzeugleiste: Suchtext (Titel, Verlag, Kommentar, ohne
    Groß-/Kleinschreibung), Typ und Status (Anzeigename aus STATUS_LABELS
    oder FILTER_ALL)."""
    if typ != FILTER_ALL and (entry.get("typ") or "").strip() != typ:
        return False
    if status != FILTER_ALL and STATUS_LABELS[status_of(entry)] != status:
        return False
    needle = search.strip().casefold()
    if needle:
        haystack = " ".join(entry.get(k) or "" for k in ("titel", "verlag", "kommentar")).casefold()
        if needle not in haystack:
            return False
    return True


def _title_key(entry: dict):
    return (entry.get("titel") or "").casefold()


def sort_entries(entries, order: str = SORT_TITEL) -> list:
    """Sortiert die Kacheln. Bei gleichem Wert (und bei Einträgen ohne Wert,
    die immer hinten stehen) entscheidet der Titel."""
    by_title = sorted(entries, key=_title_key)
    if order == SORT_VOE:
        # nur echte Termine nach vorn, chronologisch; Status/Freitext danach
        def voe_key(e):
            parsed = sorting.parse_date(next_release(e))
            return (0, parsed) if parsed else (1, 0)
        return sorted(by_title, key=voe_key)
    if order == SORT_ZUGANG:
        def zugang_key(e):
            parsed = sorting.parse_date(e.get("zugang") or "")
            return (0, -parsed.toordinal()) if parsed else (1, 0)
        return sorted(by_title, key=zugang_key)
    if order == SORT_OFFEN:
        return sorted(by_title, key=lambda e: -unread_count(e))
    return by_title


def visible_entries(entries, search="", typ=FILTER_ALL, status=FILTER_ALL, order=SORT_TITEL) -> list:
    """Gefiltert und sortiert - genau das, was die Kachelansicht zeigt."""
    return sort_entries([e for e in entries if matches(e, search, typ, status)], order)


def status_counts(entries) -> dict:
    """Anzahl je Status (Anzeigename -> Anzahl) in Legendenreihenfolge."""
    counts = dict.fromkeys(STATUS_LABELS.values(), 0)
    for e in entries:
        counts[STATUS_LABELS[status_of(e)]] += 1
    return counts
