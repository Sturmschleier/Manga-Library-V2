"""
tests/test_release_calendar.py
Tests für release_calendar.py: Termine eines Monats, Bandnummern,
Gruppierung nach Tag, Verlage, Text zum Kopieren.
"""

from datetime import date

import pytest

import release_calendar as rc


def _e(titel, verlag="Carlsen", baende_bis="3", **voe):
    return {"id": titel, "titel": titel, "verlag": verlag, "baende_bis": baende_bis, "typ": "Manga", **voe}


def test_band_numbers_follow_owned_volumes():
    releases = rc.entry_releases(_e("A", voe_1="12.11.2026", voe_2="14.01.2027", voe_3="TBA"))
    assert [(r.band, r.when, r.column) for r in releases] == [
        (4, date(2026, 11, 12), "voe_1"), (5, date(2027, 1, 14), "voe_2"),
    ]


@pytest.mark.parametrize(("owned", "band"), [("", 1), ("12 + Artbook", 13), ("x", None)])
def test_band_number_edge_cases(owned, band):
    assert rc.entry_releases(_e("A", baende_bis=owned, voe_1="12.11.2026"))[0].band == band


def test_free_text_with_band_and_date():
    r = rc.entry_releases(_e("A", baende_bis="20", voe_1="Band 25 11.06.2025"))[0]
    assert (r.band, r.when, r.exact_day) == (25, date(2025, 6, 11), True)


def test_status_texts_are_no_releases():
    assert rc.entry_releases(_e("A", voe_1="TBA", voe_2="Beendet", voe_3="Fortlaufend")) == []


def test_marks_and_new_values():
    entry = _e("A", voe_1="12.11.2026", voe_2="10.12.2026", bestellt="4", angekommen="", _neu=["voe_2"])
    first, second = rc.entry_releases(entry)
    assert (first.bestellt, first.neu) == (True, False)
    assert (second.bestellt, second.neu) == (False, True)


def test_month_view_groups_by_day_and_sorts_by_verlag():
    entries = [
        _e("Zeta", "Carlsen", voe_1="12.11.2026"),
        _e("Alpha", "Altraverse", voe_1="12.11.2026"),
        _e("Beta", "Tokyopop", voe_1="03.11.2026"),
        _e("Später", voe_1="01.12.2026"),
        _e("Nur Monat", "Egmont", voe_1="11.2026"),
    ]
    view = rc.month_view(entries, 2026, 11)
    assert [d for d, _r in view.days] == [date(2026, 11, 3), date(2026, 11, 12)]
    assert [r.titel for r in view.days[1][1]] == ["Alpha", "Zeta"]
    assert [r.titel for r in view.undated] == ["Nur Monat"]
    assert view.count == 4
    assert view.verlage == ["Altraverse", "Carlsen", "Egmont", "Tokyopop"]


def test_same_series_twice_in_a_month():
    view = rc.month_view([_e("A", voe_1="05.11.2026", voe_2="26.11.2026")], 2026, 11)
    assert [(d.day, r[0].band) for d, r in view.days] == [(5, 4), (26, 5)]


def test_verlage_of_unique_alphabetical():
    releases = rc.month_view([_e("A", "tokyopop", voe_1="05.11.2026"), _e("B", "Altraverse", voe_1="05.11.2026"),
                              _e("C", "Altraverse", voe_1="05.11.2026"), _e("D", "", voe_1="05.11.2026")],
                             2026, 11).days[0][1]
    assert rc.verlage_of(releases) == ["Altraverse", "tokyopop"]


@pytest.mark.parametrize(("start", "delta", "expected"), [
    ((2026, 11), 1, (2026, 12)), ((2026, 12), 1, (2027, 1)), ((2027, 1), -1, (2026, 12)), ((2026, 5), -17, (2024, 12)),
])
def test_shift_month(start, delta, expected):
    assert rc.shift_month(*start, delta) == expected


def test_labels():
    assert rc.month_title(2026, 3) == "März 2026"
    assert rc.day_label(date(2026, 11, 12)) == "Do, 12.11.2026"


def test_as_text_one_line_per_day_with_publishers():
    entries = [_e("Zeta", "Carlsen", voe_1="12.11.2026"), _e("Alpha", "Altraverse", voe_1="12.11.2026"),
               _e("Nur Monat", "Egmont", voe_1="11.2026")]
    text = rc.as_text(rc.month_view(entries, 2026, 11))
    assert text.splitlines() == [
        "Veröffentlichungen November 2026: 3 Bände",
        "",
        "Do, 12.11.2026  –  Altraverse, Carlsen",
        "    Alpha – Band 4  (Altraverse)",
        "    Zeta – Band 4  (Carlsen)",
        "Ohne festen Tag  –  Egmont",
        "    Nur Monat – Band 4  (Egmont)",
    ]
