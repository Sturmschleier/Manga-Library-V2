"""
tests/test_gallery.py
Tests für gallery.py: Status für die Rahmenfarben, Filter und Sortierung
der Kachelansicht, Zahlen der Seitenleiste.
"""

from datetime import date

import pytest

import gallery


def _e(titel, voe_1="", **kw):
    return {"titel": titel, "voe_1": voe_1, **kw}


def _titles(entries):
    return [e["titel"] for e in entries]


@pytest.mark.parametrize(("voe_1", "status"), [
    ("Beendet", gallery.STATUS_BEENDET),
    (" tba ", gallery.STATUS_TBA),
    ("NA", gallery.STATUS_NA),
    ("GESTOPPT", gallery.STATUS_GESTOPPT),
    ("12.10.2026", gallery.STATUS_LAUFEND),
    ("Fortlaufend", gallery.STATUS_LAUFEND),
    ("", gallery.STATUS_LAUFEND),
])
def test_status_of(voe_1, status):
    assert gallery.status_of({"voe_1": voe_1}) == status


def test_every_status_has_label_and_border_color():
    assert set(gallery.STATUS_LABELS) == set(gallery.STATUS_BORDER_COLORS)


@pytest.mark.parametrize(("value", "category"), [
    ("Beendet", "beendet"), ("tba", "tba"), ("12.10.2026", "datum"), ("11.2026", "datum"),
    ("Fortlaufend", "text"), ("", None),
])
def test_voe1_category(value, category):
    assert gallery.voe1_category(value) == category


@pytest.mark.parametrize(("owned", "read", "expected"), [("12", "10", 2), ("5", "", None), ("x", "3", None)])
def test_ruckstand(owned, read, expected):
    assert gallery.ruckstand({"baende_bis": owned, "gelesen_bis": read}) == expected


# ---------------------------------------------------------------- Filter

def test_search_covers_all_columns():
    entry = _e("One Piece", verlag="Carlsen", kommentar="Lieblingsreihe", zugang="03.2020")
    assert gallery.matches(entry, search="piece")
    assert gallery.matches(entry, search="CARLSEN")
    assert gallery.matches(entry, search="03.2020")
    assert not gallery.matches(entry, search="naruto")


def test_verlag_voe1_typ_filters():
    entry = _e("Solo Leveling", "12.10.2026", typ="Manhwa", verlag="Altraverse")
    assert gallery.matches(entry, verlag="Altraverse", voe1="Mit Datum", typ="Manhwa")
    assert not gallery.matches(entry, verlag="Carlsen")
    assert not gallery.matches(entry, voe1="TBA")
    assert not gallery.matches(entry, typ="Manga")


@pytest.mark.parametrize(("option", "ordered", "arrived", "expected"), [
    ("Bestellt", "5", "", True), ("Bestellt", "", "5", False),
    ("Angekommen", "", "5", True), ("Nicht bestellt", "", "", True), ("Nicht bestellt", "5", "", False),
])
def test_order_filter(option, ordered, arrived, expected):
    assert gallery.matches(_e("A", bestellt=ordered, angekommen=arrived), order=option) == expected


# ------------------------------------------------------------ Sortierung

def test_sort_by_title_ignores_case_and_reverses():
    entries = [_e("b"), _e("A"), _e("C")]
    assert _titles(gallery.sort_entries(entries)) == ["A", "b", "C"]
    assert _titles(gallery.sort_entries(entries, reverse=True)) == ["C", "b", "A"]


def test_sort_by_voe1_chronologically_then_text():
    entries = [_e("TBA-Reihe", "TBA"), _e("Später", "01.2027"), _e("Bald", "12.10.2026")]
    assert _titles(gallery.sort_entries(entries, "voe_1")) == ["Bald", "Später", "TBA-Reihe"]


def test_sort_by_baende_numerically():
    entries = [_e("A", baende_bis="10"), _e("B", baende_bis="9"), _e("C", baende_bis="")]
    assert _titles(gallery.sort_entries(entries, "baende_bis")) == ["B", "A", "C"]


def test_sort_by_ruckstand_keeps_missing_last():
    entries = [_e("Wenig", baende_bis="3", gelesen_bis="2"), _e("Viel", baende_bis="9", gelesen_bis="1"), _e("X")]
    assert _titles(gallery.sort_entries(entries, gallery.RUCKSTAND)) == ["Wenig", "Viel", "X"]
    assert _titles(gallery.sort_entries(entries, gallery.RUCKSTAND, reverse=True)) == ["Viel", "Wenig", "X"]


@pytest.mark.parametrize("field", ["bestellt", "angekommen"])
def test_sort_by_order_marks_puts_marked_first(field):
    entries = [_e("Ohne"), _e("Band 9", **{field: "9"}), _e("Band 4", **{field: "4"})]
    assert _titles(gallery.sort_entries(entries, field)) == ["Band 4", "Band 9", "Ohne"]
    assert _titles(gallery.sort_entries(entries, field, reverse=True)) == ["Band 9", "Band 4", "Ohne"]


def test_every_sort_option_works():
    entries = [_e("A", "TBA", baende_bis="2"), _e("B", "01.2027", bestellt="3")]
    for column, _label in gallery.SORT_OPTIONS:
        assert len(gallery.sort_entries(entries, column)) == 2


def test_visible_entries_filters_then_sorts():
    entries = [_e("Z", "Beendet"), _e("A", "TBA"), _e("M", "Beendet")]
    assert _titles(gallery.visible_entries(entries, voe1="Beendet")) == ["M", "Z"]


# --------------------------------------------------------- Seitenleiste

def test_stats_entries_can_exclude_gestoppt():
    entries = [_e("A", "Gestoppt"), _e("B", "TBA")]
    assert _titles(gallery.stats_entries(entries, exclude_gestoppt=True)) == ["B"]
    assert len(gallery.stats_entries(entries)) == 2


def test_totals():
    entries = [_e("A", baende_bis="10", gelesen_bis="5"), _e("B", baende_bis="6", gelesen_bis="x")]
    assert gallery.totals(entries) == {"besitz": 16, "gelesen": 5, "differenz": 11, "anteil": 31.25}
    assert gallery.totals([])["anteil"] == 0.0


def test_counts_by_most_first_then_alphabetical():
    entries = [_e("A", verlag="Carlsen"), _e("B", verlag="altraverse"), _e("C", verlag="Carlsen"), _e("D")]
    assert gallery.counts_by(entries, "verlag") == [("Carlsen", 2), ("altraverse", 1)]


def test_typ_balance():
    entries = [_e("A", typ="Manga", baende_bis="10", gelesen_bis="4"),
               _e("B", typ="Manga", baende_bis="2", gelesen_bis="2"),
               _e("C", typ="Light Novel", baende_bis="3")]
    assert gallery.typ_balance(entries) == [("Manga", 12, 6, 6), ("Light Novel", 3, 0, 3)]


def test_release_counts_over_all_voe_columns():
    today = date(2026, 12, 5)
    entries = [
        _e("A", "12.12.2026", voe_2="01.2027", voe_3="TBA"),
        _e("B", "02.02.2027"),
        _e("C", "11.2026"),     # vor dem aktuellen Monat: ausstehend
        _e("D", "Beendet"),
    ]
    assert gallery.release_counts(entries, today) == ([1, 1, 1], 1)


def test_status_counts_in_legend_order():
    counts = gallery.status_counts([_e("A", "Beendet"), _e("B", "Beendet"), _e("C", "01.2027")])
    assert list(counts) == list(gallery.STATUS_LABELS.values())
    assert counts["Beendet"] == 2
    assert counts["Laufend"] == 1


# ------------------------------------------------------------ Kachelraster

def test_grid_columns_like_max_extent():
    assert gallery.grid_columns(1000, 220, 14) == 5     # 1000 / 234 = 4,3 -> 5 Spalten à ~189 px
    assert gallery.grid_columns(400, 200, 14) == 2
    assert gallery.grid_columns(100, 220, 14) == 1


def test_grid_columns_large_tiles_are_wider():
    # Handy hochkant: normal 2 Spalten, groß 1 Spalte (vorher auch 2)
    assert gallery.grid_columns(400, 200, 14, 1.5) == 1
    # PC: 5 normale Spalten à ~189 px -> 3 große à ~324 px
    assert gallery.grid_columns(1000, 220, 14, 1.5) == 3
    # nie mehr als eine Spalte
    assert gallery.grid_columns(100, 220, 14, 1.5) == 1


def test_tile_aspect_fills_cover_width():
    aspect = gallery.tile_aspect(414, 2, 14, 0.72, 198)
    tile_w = 200
    assert aspect == pytest.approx(tile_w / (tile_w / 0.72 + 198))

