"""
gallery.py
Logik der Kachelansicht ohne Flet: Status eines Werks (für die farbigen
Rahmen), Filter und Sortierung der Kacheln sowie die Zahlen der
Seitenleiste. Bewusst ohne Oberfläche, damit sie sich direkt testen lässt -
ui/ ruft nur diese Funktionen auf. Filter, Statistik und Termin-Zähler
rechnen genau wie die Tabellenansicht von Version 1.

Der Status steht wie in Version 1 in der Spalte "VÖ +1" (voe_1): "Beendet",
"TBA", "NA" oder "Gestoppt". Alles andere (ein Datum, "Fortlaufend",
Freitext wie "Band 17 11.06.2025") gilt als laufende Reihe.
"""

from datetime import date
from typing import Optional

import database as db
import logic
import sorting
from logic import parse_int

STATUS_LAUFEND = "laufend"
STATUS_BEENDET = "beendet"
STATUS_TBA = "tba"
STATUS_NA = "na"
STATUS_GESTOPPT = "gestoppt"

# Reihenfolge = Reihenfolge in der Legende
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

# VÖ +1-Filter wie in Version 1: bekannte Status-Werte + "Mit Datum" für
# alles, was ein tatsächlicher Termin (kein Status-Text) ist
VOE1_FILTER_OPTIONS = ["Alle", "Beendet", "TBA", "Gestoppt", "NA", "Mit Datum"]
_VOE1_STATUS_KEYS = {"beendet", "tba", "gestoppt", "na"}

# Berechnete Spalte wie in Version 1: Bände (bis) minus Gelesen bis
RUCKSTAND = "ruckstand"

# Sortierung: (Schlüssel, Anzeigename) - Schlüssel sind die Spalten der
# Datenbank, dazu Rückstand und die Bestell-Markierungen
SORT_OPTIONS = [
    ("titel", "Titel"),
    ("baende_bis", "Bände (bis)"),
    ("gelesen_bis", "Gelesen bis"),
    (RUCKSTAND, "Rückstand"),
    ("typ", "Typ"),
    ("verlag", "Verlag"),
    ("zugang", "Zugang"),
    ("voe_1", "VÖ +1"),
    ("komplett", "Komplett"),
    ("beendet", "Beendet"),
    ("bestellt", "Bestellt"),
    ("angekommen", "Angekommen (geliefert)"),
]
SORT_LABELS = dict(SORT_OPTIONS)


def status_of(entry: dict) -> str:
    """Status eines Werks aus "VÖ +1" (siehe Moduldoku)."""
    value = (entry.get("voe_1") or "").strip().lower()
    if value in (STATUS_BEENDET, STATUS_TBA, STATUS_NA, STATUS_GESTOPPT):
        return value
    return STATUS_LAUFEND


def voe1_category(value) -> Optional[str]:
    """Ordnet einen VÖ+1-Wert einer Filterkategorie zu: einem der bekannten
    Status-Texte, "datum" für eine echte erkannte Terminangabe, oder
    "text" für sonstigen Freitext (z.B. "Fortlaufend", "Band 17 ...")."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in _VOE1_STATUS_KEYS:
        return v
    if sorting.parse_date(value):
        return "datum"
    return "text"


def ruckstand(entry: dict) -> Optional[int]:
    """Bände (bis) minus Gelesen bis, None wenn eines der beiden Felder keine
    gültige Zahl enthält (wie die Spalte "Rückstand" in Version 1)."""
    besitz = parse_int(entry.get("baende_bis"))
    gelesen = parse_int(entry.get("gelesen_bis"))
    if besitz is None or gelesen is None:
        return None
    return besitz - gelesen


# ---------------------------------------------------------------- Filter

def matches(entry: dict, search: str = "", verlag: str = FILTER_ALL, voe1: str = FILTER_ALL,
            order: str = logic.ORDER_FILTER_ALL, typ: str = FILTER_ALL) -> bool:
    """Filter wie in Version 1: Suchtext in irgendeiner Spalte (ohne Groß-/
    Kleinschreibung), Verlag, VÖ +1 (VOE1_FILTER_OPTIONS), Bestellstatus
    (logic.ORDER_FILTER_OPTIONS) - dazu der Typ."""
    needle = search.strip().lower()
    if needle and not any(needle in (entry.get(c) or "").lower() for c in db.COLUMN_NAMES):
        return False
    if verlag != FILTER_ALL and (entry.get("verlag") or "").strip() != verlag:
        return False
    if voe1 != FILTER_ALL:
        wanted = "datum" if voe1 == "Mit Datum" else voe1.lower()
        if voe1_category(entry.get("voe_1")) != wanted:
            return False
    if order != logic.ORDER_FILTER_ALL and not logic.matches_order_filter(entry, order):
        return False
    return typ == FILTER_ALL or (entry.get("typ") or "").strip() == typ


# ------------------------------------------------------------ Sortierung

def _mark_key(entry: dict, field: str):
    """Markierte zuerst (nach Bandnummer), unmarkierte danach."""
    band = parse_int(entry.get(field))
    if band is None:
        return (1, 0) if not (entry.get(field) or "").strip() else (0, 0)
    return (0, band)


def sort_entries(entries, column: str = "titel", reverse: bool = False) -> list:
    """Sortiert wie die Spaltenköpfe in Version 1 (sorting.sort_key: Daten
    chronologisch, Zahlen numerisch, Leeres zuletzt). Bei gleichem Wert
    entscheidet der Titel. Rückstand ohne Zahl und unmarkierte Einträge
    (Bestellt/Angekommen) stehen immer hinten."""
    rows = sorted(entries, key=lambda e: (e.get("titel") or "").casefold())
    if column == "titel":
        return list(reversed(rows)) if reverse else rows
    if column == RUCKSTAND:
        with_value = [e for e in rows if ruckstand(e) is not None]
        without = [e for e in rows if ruckstand(e) is None]
        return sorted(with_value, key=ruckstand, reverse=reverse) + without
    if column in logic.MARK_FIELDS:
        marked = [e for e in rows if (e.get(column) or "").strip()]
        unmarked = [e for e in rows if not (e.get(column) or "").strip()]
        return sorted(marked, key=lambda e: _mark_key(e, column), reverse=reverse) + unmarked
    return sorted(rows, key=lambda e: sorting.sort_key(column, e.get(column)), reverse=reverse)


def visible_entries(entries, search="", verlag=FILTER_ALL, voe1=FILTER_ALL, order=logic.ORDER_FILTER_ALL,
                    typ=FILTER_ALL, sort_column="titel", reverse=False) -> list:
    """Gefiltert und sortiert - genau das, was die Kachelansicht zeigt."""
    shown = [e for e in entries if matches(e, search, verlag, voe1, order, typ)]
    return sort_entries(shown, sort_column, reverse)


# --------------------------------------------------------- Seitenleiste

def stats_entries(entries, exclude_gestoppt: bool = False) -> list:
    """Die Einträge für Summen und Bilanzen - ohne "Gestoppt", wenn die
    Option "Gestoppt: keine Berechnung" aktiv ist."""
    if exclude_gestoppt:
        return [e for e in entries if (e.get("voe_1") or "").strip().lower() != "gestoppt"]
    return list(entries)


def _int_or_zero(value) -> int:
    return parse_int(value) or 0


def totals(entries) -> dict:
    """Statistik-Box: Summe im Besitz, Summe gelesen, Differenz, Anteil in %."""
    besitz = sum(_int_or_zero(e.get("baende_bis")) for e in entries)
    gelesen = sum(_int_or_zero(e.get("gelesen_bis")) for e in entries)
    return {
        "besitz": besitz,
        "gelesen": gelesen,
        "differenz": besitz - gelesen,
        "anteil": (gelesen / besitz * 100) if besitz else 0.0,
    }


def counts_by(entries, column: str) -> list:
    """[(Wert, Anzahl)] - meiste zuerst, dann alphabetisch; leere Werte zählen nicht."""
    counts = {}
    for e in entries:
        value = (e.get(column) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def typ_balance(entries) -> list:
    """[(Typ, Gesamt, Gelesen, Offen)] je Typ - größte Sammlung zuerst."""
    buckets = {}
    for e in entries:
        typ = (e.get("typ") or "").strip()
        if not typ:
            continue
        bucket = buckets.setdefault(typ, [0, 0])
        bucket[0] += _int_or_zero(e.get("baende_bis"))
        bucket[1] += _int_or_zero(e.get("gelesen_bis"))
    rows = [(typ, g, r, g - r) for typ, (g, r) in buckets.items()]
    return sorted(rows, key=lambda row: (-row[1], row[0].lower()))


def voe_dates(entry: dict) -> list:
    """Alle echten Termine in VÖ +1 bis VÖ +3 als [(Spalte, date)]."""
    found = []
    for col in db.VOE_COLUMNS:
        parsed = sorting.parse_date(entry.get(col))
        if parsed is not None:
            found.append((col, parsed))
    return found


def release_counts(entries, today: Optional[date] = None) -> tuple:
    """([aktueller, nächster, übernächster Monat], vor aktuellem Monat) -
    gezählt werden Termine über alle drei VÖ-Spalten, nicht Titel."""
    today = today or date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(3):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    counts = [0, 0, 0]
    overdue = 0
    for entry in entries:
        for _col, parsed in voe_dates(entry):
            key = (parsed.year, parsed.month)
            if key in months:
                counts[months.index(key)] += 1
            elif key < (today.year, today.month):
                overdue += 1
    return counts, overdue


def status_counts(entries) -> dict:
    """Anzahl je Status (Anzeigename -> Anzahl) in Legendenreihenfolge."""
    counts = dict.fromkeys(STATUS_LABELS.values(), 0)
    for e in entries:
        counts[STATUS_LABELS[status_of(e)]] += 1
    return counts
