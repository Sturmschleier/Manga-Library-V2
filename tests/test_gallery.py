"""
tests/test_gallery.py
Tests für gallery.py: Status für die Rahmenfarben, Filtern und Sortieren
der Kachelansicht.
"""

import pytest

import gallery


def _e(titel, voe_1="", **kw):
    return {"titel": titel, "voe_1": voe_1, **kw}


@pytest.mark.parametrize(("voe_1", "status"), [
    ("Beendet", gallery.STATUS_BEENDET),
    (" tba ", gallery.STATUS_TBA),
    ("NA", gallery.STATUS_NA),
    ("GESTOPPT", gallery.STATUS_GESTOPPT),
    ("12.10.2026", gallery.STATUS_LAUFEND),
    ("Fortlaufend", gallery.STATUS_LAUFEND),
    ("Band 17 11.06.2025", gallery.STATUS_LAUFEND),
    ("", gallery.STATUS_LAUFEND),
])
def test_status_of(voe_1, status):
    assert gallery.status_of({"voe_1": voe_1}) == status


def test_every_status_has_label_and_border_color():
    assert set(gallery.STATUS_LABELS) == set(gallery.STATUS_BORDER_COLORS)


def test_next_release_only_for_running_series():
    assert gallery.next_release(_e("A", "12.10.2026")) == "12.10.2026"
    assert gallery.next_release(_e("A", "TBA")) == ""


@pytest.mark.parametrize(("owned", "read", "unread"), [
    ("12", "10", 2), ("5", "", 5), ("", "", 0), ("x", "3", 0), ("3", "5", 0),
])
def test_unread_count(owned, read, unread):
    assert gallery.unread_count({"baende_bis": owned, "gelesen_bis": read}) == unread


def test_matches_search_is_case_insensitive_over_title_verlag_kommentar():
    entry = _e("One Piece", verlag="Carlsen", kommentar="Lieblingsreihe")
    assert gallery.matches(entry, search="piece")
    assert gallery.matches(entry, search="CARLSEN")
    assert gallery.matches(entry, search="lieblings")
    assert not gallery.matches(entry, search="naruto")


def test_matches_typ_and_status_filters():
    entry = _e("Solo Leveling", "Beendet", typ="Manhwa")
    assert gallery.matches(entry, typ="Manhwa", status="Beendet")
    assert not gallery.matches(entry, typ="Manga")
    assert not gallery.matches(entry, status="TBA")
    assert gallery.matches(entry, typ=gallery.FILTER_ALL, status=gallery.FILTER_ALL)


def test_sort_by_title_ignores_case():
    entries = [_e("b"), _e("A"), _e("C")]
    assert [e["titel"] for e in gallery.sort_entries(entries)] == ["A", "b", "C"]


def test_sort_by_next_release_puts_dates_first_chronologically():
    entries = [_e("TBA-Reihe", "TBA"), _e("Später", "01.2027"), _e("Bald", "12.10.2026"), _e("Auch bald", "12.10.2026")]
    order = [e["titel"] for e in gallery.sort_entries(entries, gallery.SORT_VOE)]
    assert order == ["Auch bald", "Bald", "Später", "TBA-Reihe"]


def test_sort_by_zugang_newest_first_without_date_last():
    entries = [_e("Alt", zugang="01.2020"), _e("Ohne"), _e("Neu", zugang="05.2026")]
    assert [e["titel"] for e in gallery.sort_entries(entries, gallery.SORT_ZUGANG)] == ["Neu", "Alt", "Ohne"]


def test_sort_by_unread_most_first():
    entries = [_e("Wenig", baende_bis="3", gelesen_bis="2"), _e("Viel", baende_bis="9", gelesen_bis="1")]
    assert [e["titel"] for e in gallery.sort_entries(entries, gallery.SORT_OFFEN)] == ["Viel", "Wenig"]


def test_visible_entries_filters_then_sorts():
    entries = [_e("Z", "Beendet"), _e("A", "TBA"), _e("M", "Beendet")]
    shown = gallery.visible_entries(entries, status="Beendet")
    assert [e["titel"] for e in shown] == ["M", "Z"]


def test_status_counts_in_legend_order():
    counts = gallery.status_counts([_e("A", "Beendet"), _e("B", "Beendet"), _e("C", "01.2027")])
    assert list(counts) == list(gallery.STATUS_LABELS.values())
    assert counts["Beendet"] == 2
    assert counts["Laufend"] == 1
    assert counts["NA"] == 0
