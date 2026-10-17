"""
release_calendar.py
Monatlicher Veröffentlichungskalender ohne Oberfläche: sammelt aus den
VÖ-Spalten (VÖ +1 bis VÖ +3) aller Einträge die Termine eines Monats und
gruppiert sie nach Erscheinungstag.

- VÖ +1 ist der nächste Band nach "Bände (bis)", VÖ +2 der übernächste usw.
  - daraus ergibt sich die Bandnummer.
- Freitext der Form "Band 17 11.06.2025" nennt Band und Datum selbst.
- Termine nur mit Monat ("11.2026") haben keinen festen Tag; sie stehen
  getrennt am Ende des Monats.
- Status-Texte ("TBA", "Beendet" ...) sind keine Termine und fehlen hier.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import database as db
import logic
import sorting

WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember")

_DAY_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")
_BAND_DATE_RE = re.compile(r"^band\s+(\d+)\s+(\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\.\d{4})$", re.IGNORECASE)


@dataclass
class Release:
    entry_id: object
    titel: str
    verlag: str
    typ: str
    band: Optional[int]       # None, wenn "Bände (bis)" keine Zahl ist
    column: str               # voe_1 / voe_2 / voe_3
    when: date                # bei Terminen ohne Tag der Monatserste
    exact_day: bool           # False bei "MM.JJJJ"
    neu: bool = False         # vom Abgleich mit buchhandel.de, noch nicht gespeichert
    bestellt: bool = False    # genau dieser Band ist als bestellt markiert
    abholbereit: bool = False


def _owned(entry: dict) -> Optional[int]:
    """Vorhandene Bände; leer zählt als 0, "12 + Artbook" als 12."""
    raw = str(entry.get("baende_bis") or "").strip()
    if not raw:
        return 0
    value = logic.parse_int(raw)
    if value is None:
        m = re.search(r"\d+", raw)
        value = int(m.group()) if m else None
    return value


def _parse(value: str):
    """(Datum, genauer Tag?, Band aus dem Text oder None), sonst None."""
    value = (value or "").strip()
    band = None
    m = _BAND_DATE_RE.match(value)
    if m:
        band, value = int(m.group(1)), m.group(2)
    parsed = sorting.parse_date(value)
    if parsed is None:
        return None
    return parsed, bool(_DAY_RE.match(value)), band


def entry_releases(entry: dict) -> list:
    """Alle Termine eines Eintrags als Release-Liste."""
    owned = _owned(entry)
    new_columns = logic.new_value_columns(entry)
    marks = {field: logic.parse_int(entry.get(field)) for field in logic.MARK_FIELDS}
    result = []
    for position, column in enumerate(db.VOE_COLUMNS, start=1):
        parsed = _parse(entry.get(column))
        if parsed is None:
            continue
        when, exact, band = parsed
        if band is None and owned is not None:
            band = owned + position
        result.append(Release(
            entry_id=entry.get("id"), titel=(entry.get("titel") or "").strip(),
            verlag=(entry.get("verlag") or "").strip(), typ=(entry.get("typ") or "").strip(),
            band=band, column=column, when=when, exact_day=exact, neu=column in new_columns,
            bestellt=band is not None and marks["bestellt"] == band,
            abholbereit=band is not None and marks["angekommen"] == band,
        ))
    return result


@dataclass
class MonthView:
    year: int
    month: int
    days: list        # [(date, [Release])] - aufsteigend nach Tag
    undated: list     # [Release] - nur Monat bekannt

    @property
    def count(self) -> int:
        return sum(len(r) for _d, r in self.days) + len(self.undated)

    @property
    def verlage(self) -> list:
        return verlage_of([r for _d, rs in self.days for r in rs] + self.undated)


def _sort_key(r: Release):
    return (r.verlag.casefold(), r.titel.casefold(), r.band or 0)


def month_view(entries, year: int, month: int) -> MonthView:
    """Alle Termine eines Monats, gruppiert nach Tag; innerhalb eines Tages
    nach Verlag und Titel sortiert."""
    by_day = {}
    undated = []
    for entry in entries:
        for r in entry_releases(entry):
            if (r.when.year, r.when.month) != (year, month):
                continue
            if r.exact_day:
                by_day.setdefault(r.when, []).append(r)
            else:
                undated.append(r)
    days = [(day, sorted(by_day[day], key=_sort_key)) for day in sorted(by_day)]
    return MonthView(year, month, days, sorted(undated, key=_sort_key))


def verlage_of(releases) -> list:
    """Verlage einer Release-Liste: einmal je Verlag, alphabetisch."""
    return sorted({r.verlag for r in releases if r.verlag}, key=str.casefold)


def shift_month(year: int, month: int, delta: int) -> tuple:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_title(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def day_label(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.%Y')}"


def release_label(r: Release) -> str:
    return f"{r.titel} – Band {r.band}" if r.band is not None else r.titel


def as_text(view: MonthView) -> str:
    """Der Monat als Text zum Kopieren - eine Zeile je Erscheinungstag mit
    den Verlagen, darunter die Titel."""
    lines = [f"Veröffentlichungen {month_title(view.year, view.month)}: {view.count} Bände", ""]
    for day, releases in view.days:
        lines.append(f"{day_label(day)}  –  {', '.join(verlage_of(releases))}")
        lines += [f"    {release_label(r)}  ({r.verlag})" if r.verlag else f"    {release_label(r)}"
                  for r in releases]
    if view.undated:
        lines.append(f"Ohne festen Tag  –  {', '.join(verlage_of(view.undated))}")
        lines += [f"    {release_label(r)}  ({r.verlag})" if r.verlag else f"    {release_label(r)}"
                  for r in view.undated]
    return "\n".join(lines)
