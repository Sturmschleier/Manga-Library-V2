"""
tests/test_covers.py
Tests für covers.py: Suche nach Band 1 bei der DNB (Netzwerk simuliert),
Zwischenspeicher-Tabelle, Bilddateien und eigene Cover.
"""

import xml.etree.ElementTree as ET

import pytest

import covers
import database as db
import isbn_lookup

MARC_NS = "http://www.loc.gov/MARC21/slim"
ALBUS_1 = "9783753943190"
ONE_PIECE_1 = "9783551744913"
PARTY_1 = "9783551718433"


def _record(titel, band, year, isbn="", series=None, publisher="Carlsen"):
    """Minimaler MARC-Record: 245 (Titel + Band), optional 490/830 (Reihe),
    264 (Verlag + Jahr), 020 (ISBN)."""
    fields = [("245", [("a", titel), ("n", str(band))])]
    if series:
        fields += [("490", [("a", series), ("v", str(band))]), ("830", [("a", series), ("v", str(band))])]
    fields.append(("264", [("b", publisher), ("c", str(year))]))
    if isbn:
        fields.append(("020", [("a", isbn)]))
    xml = f'<record xmlns="{MARC_NS}">'
    for tag, subfields in fields:
        xml += f'<datafield tag="{tag}">' + "".join(
            f'<subfield code="{c}">{t}</subfield>' for c, t in subfields) + "</datafield>"
    return ET.fromstring(xml + "</record>")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Kein Test darf DNB oder VLB wirklich fragen."""
    def blocked(*args, **kwargs):
        raise AssertionError("echte Netzanfrage im Test")

    monkeypatch.setattr(covers.requests, "get", blocked)
    monkeypatch.setattr(covers.vlb_lookup.requests, "get", blocked)


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_FILE", tmp_path / "manga_library.db")
    monkeypatch.setattr(covers, "COVER_DIR", tmp_path / "covers")
    covers.ensure_table()
    return tmp_path


@pytest.fixture
def fake_dnb(monkeypatch):
    """Ersetzt die SRU-Anfrage: `pages` ordnet einen Teil der Anfrage
    (z.B. "jhr<2026") den Records zu; die erste passende Regel gewinnt,
    "" passt immer. Alle Anfragen landen in `queries`."""
    state = {"pages": [], "queries": []}

    def fetch(query, label, log=None):
        state["queries"].append(query)
        for needle, records in state["pages"]:
            if needle in query:
                return records
        return []

    monkeypatch.setattr(isbn_lookup, "fetch_dnb_records", fetch)
    monkeypatch.setattr(isbn_lookup, "REQUEST_DELAY_SECONDS", 0)
    return state


# ------------------------------------------------------------ Titel/Reihe

@pytest.mark.parametrize(("titel", "expected"), [
    ("Accel World – Light Novel", "Accel World"),
    ("Overlord (Manga)", "Overlord"),
    ("Solo Leveling", "Solo Leveling"),
    ("Manga", "Manga"),   # nur der Zusatz - dann bleibt der Titel
])
def test_search_title_strips_type_suffix(titel, expected):
    assert covers.search_title(titel) == expected


def test_series_matches_own_series_but_not_spin_off():
    assert covers.series_matches(_record("One piece", 1, 2011), "One Piece")
    assert not covers.series_matches(_record("One piece party", 1, 2017), "One Piece")


def test_series_matches_decomposed_umlauts_and_series_field():
    # DNB liefert "ä" zerlegt (a + Trema); Titel des Bandes steht in 245, die Reihe in 490
    record = _record("Albus verändert die Welt 01", 1, 2021, series="Albus verändert die Welt")
    assert covers.series_matches(record, "Albus verändert die Welt")


# ---------------------------------------------------------- Band-1-Suche

def test_find_band1_on_first_page(fake_dnb):
    fake_dnb["pages"] = [("", [_record("Albus verändert die Welt", 1, 2021, ALBUS_1, publisher="Altraverse")])]
    assert covers.find_band1_isbn("Albus verändert die Welt", "Altraverse", "Manga") == ALBUS_1
    assert len(fake_dnb["queries"]) == 1


def test_find_band1_pages_back_in_time_and_ignores_spin_offs(fake_dnb):
    newest = [_record("One piece", 90 + i, 2026) for i in range(19)] + [_record("One piece party", 1, 2026, PARTY_1)]
    fake_dnb["pages"] = [
        ("jhr<2026", [_record("One piece", 1, 2011, ONE_PIECE_1), _record("One piece", 2, 2011)]),
        ("", newest),
    ]
    assert covers.find_band1_isbn("One Piece", "Carlsen", "Manga") == ONE_PIECE_1
    assert "jhr<2026" in fake_dnb["queries"][1]


def test_find_band1_stops_on_short_page_and_skips_pass_without_publisher(fake_dnb):
    fake_dnb["pages"] = [("", [_record("One piece", 5, 2015)])]
    assert covers.find_band1_isbn("One Piece", "Carlsen", "Manga") is None
    # nur 1 Treffer (< 20): fertig; die Reihe gibt es beim Verlag - keine Suche ohne Verlag
    assert len(fake_dnb["queries"]) == 1


def test_find_band1_tries_without_publisher_when_series_unknown_there(fake_dnb):
    fake_dnb["pages"] = [("vlg=", []), ("", [_record("Solo leveling", 1, 2023, ALBUS_1, publisher="Andere")])]
    assert covers.find_band1_isbn("Solo Leveling", "Altraverse", "Manhwa") == ALBUS_1
    assert len(fake_dnb["queries"]) == 2


def test_series_match_levels():
    assert covers.series_match(_record("One piece", 1, 2011), "One Piece") == covers.SERIES_EXACT
    assert covers.series_match(_record("One piece - Heroines", 1, 2027), "One Piece") == covers.SERIES_SUBTITLE
    assert covers.series_match(_record("Overlord: Das Buch", 1, 2020), "Overlord") == covers.SERIES_SUBTITLE
    assert covers.series_match(_record("One piece party", 1, 2017), "One Piece") == covers.SERIES_NONE


def test_find_band1_prefers_exact_series_over_subtitle_spin_off(fake_dnb):
    heroines = _record("One piece - Heroines", 1, 2027, PARTY_1)
    newest = [heroines] + [_record("One piece", 90 + i, 2026) for i in range(19)]
    fake_dnb["pages"] = [("jhr<2026", [_record("One piece", 1, 2011, ONE_PIECE_1)]), ("", newest)]
    assert covers.find_band1_isbn("One Piece", "Carlsen", "Manga") == ONE_PIECE_1


def test_find_band1_falls_back_to_oldest_subtitled_series(fake_dnb):
    zero = _record("Arifureta - Zero", 1, 2023, PARTY_1, publisher="Altraverse")
    main = _record("Arifureta - der Kampf zurück in meine Welt", 1, 2019, ALBUS_1, publisher="Altraverse")
    fake_dnb["pages"] = [("jhr<2023", [main]), ("", [zero] + [_record("Arifureta - Zero", 2, 2024)] * 19)]
    assert covers.find_band1_isbn("Arifureta", "Altraverse", "Manga") == ALBUS_1


@pytest.mark.parametrize(("years", "before", "expected"), [
    ([2026, 2025], None, 2025),
    ([2026, 2025], 2025, 2024),   # Jahr im Datensatz weicht vom Suchindex ab: trotzdem weiter
    ([2019], 2025, 2019),
    ([], None, None),
    ([], 2025, 2024),
])
def test_next_year_bound(years, before, expected):
    records = [_record("X", 3, y) for y in years] or [_record("X", 3, "o. J.")]
    assert covers._next_year_bound(records, before) == expected


# ------------------------------------------------- Wann wird gesucht?

def test_needs_lookup():
    assert covers.needs_lookup(None)
    assert not covers.needs_lookup(covers.CoverInfo("A", quelle=covers.QUELLE_DNB, geprueft_am="2026-01-01"))
    assert not covers.needs_lookup(covers.CoverInfo("A", quelle=covers.QUELLE_EIGEN))
    assert not covers.needs_lookup(covers.CoverInfo("A", quelle=covers.QUELLE_ENTFERNT, geprueft_am="2020-01-01"))
    erfolglos = covers.CoverInfo("A", quelle=covers.QUELLE_KEINE, geprueft_am="2026-10-01")
    assert not covers.needs_lookup(erfolglos, today="2026-10-17")
    assert covers.needs_lookup(erfolglos, today="2026-11-01")   # nach RETRY_DAYS erneut


def test_pending_skips_known_and_empty_titles():
    entries = [{"titel": "A"}, {"titel": "B"}, {"titel": ""}, {"titel": "A"}]
    infos = {"B": covers.CoverInfo("B", quelle=covers.QUELLE_DNB)}
    assert [e["titel"] for e in covers.pending(entries, infos)] == ["A"]


# ------------------------------------------------- Speichern und Dateien

def test_lookup_and_store_saves_image_and_row(tmp_data, monkeypatch):
    monkeypatch.setattr(covers, "find_band1_isbn", lambda *a, **kw: ALBUS_1)
    monkeypatch.setattr(covers, "download_cover", lambda isbn: b"JPEG" * 500)
    info = covers.lookup_and_store("Albus verändert die Welt", "Altraverse", "Manga")
    assert info.quelle == covers.QUELLE_DNB
    assert info.path.read_bytes() == b"JPEG" * 500
    assert covers.load_all()["Albus verändert die Welt"].isbn == ALBUS_1


def test_lookup_and_store_remembers_failure(tmp_data, monkeypatch):
    monkeypatch.setattr(covers, "find_band1_isbn", lambda *a, **kw: ALBUS_1)
    monkeypatch.setattr(covers, "download_cover", lambda isbn: None)
    monkeypatch.setattr(covers, "download_vlb_cover", lambda isbn: None)
    info = covers.lookup_and_store("A", "V", "Manga")
    assert (info.quelle, info.isbn, info.path) == (covers.QUELLE_KEINE, ALBUS_1, None)
    assert not covers.needs_lookup(covers.load_all()["A"])


def test_set_custom_copies_image_and_replaces_older_one(tmp_data):
    png = tmp_data / "bild.png"
    png.write_bytes(b"PNG")
    jpg = tmp_data / "bild.jpg"
    jpg.write_bytes(b"JPG")
    covers.set_custom("Titel", png)
    info = covers.set_custom("Titel", jpg)
    assert info.quelle == covers.QUELLE_EIGEN
    assert info.path.read_bytes() == b"JPG"
    assert [p.suffix for p in covers.COVER_DIR.iterdir()] == [".jpg"]


def test_set_custom_rejects_non_images(tmp_data):
    text = tmp_data / "notiz.txt"
    text.write_text("x")
    with pytest.raises(ValueError):
        covers.set_custom("Titel", text)


def test_remove_and_forget(tmp_data):
    covers.remove("Titel")
    assert covers.load_all()["Titel"].quelle == covers.QUELLE_ENTFERNT
    covers.forget("Titel")
    assert "Titel" not in covers.load_all()


class _Resp:
    def __init__(self, status, content_type, content):
        self.status_code, self.headers, self.content = status, {"content-type": content_type}, content


@pytest.mark.parametrize(("resp", "ok"), [
    (_Resp(200, "image/jpeg; charset=UTF-8", b"x" * 5000), True),
    (_Resp(404, "text/html;charset=utf-8", b"x" * 5000), False),
    (_Resp(200, "text/html", b"x" * 5000), False),
    (_Resp(200, "image/gif", b"x" * 43), False),   # Platzhalter-Pixel
])
def test_download_cover_accepts_only_real_images(monkeypatch, resp, ok):
    monkeypatch.setattr(covers.requests, "get", lambda *a, **kw: resp)
    assert (covers.download_cover(ALBUS_1) is not None) == ok


# ------------------------------------------------------ VLB-Ausweichlösung

def _vlb_product(title, isbn, datum="09.03.2015", publisher="TOKYOPOP GmbH"):
    return {"title": title, "identifier": isbn, "publicationDate": datum, "publisher": publisher,
            "productType": "pbook"}


def test_find_band1_vlb_picks_band_1_of_the_right_edition(monkeypatch):
    calls = []

    def fetch(query, session=None, newest_first=True):
        calls.append((query, newest_first))
        return [_vlb_product("Accel World 01", PARTY_1), _vlb_product("Accel World - Novel 01", ALBUS_1),
                _vlb_product("Accel World - Novel 02", ONE_PIECE_1, "08.06.2015")]

    monkeypatch.setattr(covers.vlb_lookup, "fetch_products", fetch)
    assert covers.find_band1_vlb("Accel World – Light Novel", "Tokyopop", "Light Novel") == ALBUS_1
    assert covers.find_band1_vlb("Accel World", "Tokyopop", "Manga") == PARTY_1
    assert calls[0] == ("(ti=Accel World) und pt=pbook", False)   # ohne Jahresgrenze, älteste zuerst


def test_find_band1_vlb_retries_without_subtitle(monkeypatch):
    queries = []

    def fetch(query, session=None, newest_first=True):
        queries.append(query)
        return [_vlb_product("A Wild Last Boss Appeared! 01", ALBUS_1)] if len(queries) == 2 else []

    monkeypatch.setattr(covers.vlb_lookup, "fetch_products", fetch)
    monkeypatch.setattr(covers.vlb_lookup, "REQUEST_DELAY_SECONDS", 0)
    isbn = covers.find_band1_vlb("A Wild Last Boss Appeared! – Der Overlord", "Tokyopop", "Manga")
    assert isbn == ALBUS_1
    assert queries[1] == "(ti=A Wild Last Boss Appeared!) und pt=pbook"


def test_lookup_uses_vlb_image_for_dnb_isbn(tmp_data, monkeypatch):
    monkeypatch.setattr(covers, "find_band1_isbn", lambda *a, **kw: ALBUS_1)
    monkeypatch.setattr(covers, "download_cover", lambda isbn: None)
    monkeypatch.setattr(covers, "download_vlb_cover", lambda isbn: b"VLB" * 500)
    info = covers.lookup_and_store("A", "V", "Manga")
    assert (info.quelle, info.isbn) == (covers.QUELLE_VLB, ALBUS_1)
    assert info.path.read_bytes() == b"VLB" * 500


def test_lookup_searches_vlb_when_dnb_has_no_isbn(tmp_data, monkeypatch):
    monkeypatch.setattr(covers, "find_band1_isbn", lambda *a, **kw: None)
    monkeypatch.setattr(covers, "find_band1_vlb", lambda *a, **kw: ONE_PIECE_1)
    monkeypatch.setattr(covers, "download_vlb_cover", lambda isbn: b"V" * 2000)
    info = covers.lookup_and_store("A", "V", "Manga")
    assert (info.quelle, info.isbn) == (covers.QUELLE_VLB, ONE_PIECE_1)
    assert not covers.needs_lookup(info)


def test_lookup_without_vlb(tmp_data, monkeypatch):
    monkeypatch.setattr(covers, "find_band1_isbn", lambda *a, **kw: None)
    monkeypatch.setattr(covers, "find_band1_vlb", lambda *a, **kw: pytest.fail("VLB darf nicht gefragt werden"))
    assert covers.lookup_and_store("A", use_vlb=False).quelle == covers.QUELLE_KEINE


def test_refresh_targets(tmp_data):
    found = tmp_data / "covers" / "x.jpg"
    found.parent.mkdir()
    found.write_bytes(b"x")
    infos = {
        "Gefunden": covers.CoverInfo("Gefunden", datei="x.jpg", quelle=covers.QUELLE_VLB),
        "Eigen": covers.CoverInfo("Eigen", datei="x.jpg", quelle=covers.QUELLE_EIGEN),
        "Keins": covers.CoverInfo("Keins", quelle=covers.QUELLE_KEINE),
        "Entfernt": covers.CoverInfo("Entfernt", quelle=covers.QUELLE_ENTFERNT),
    }
    entries = [{"titel": t} for t in ("Gefunden", "Eigen", "Keins", "Entfernt", "Neu", "Neu")]
    assert [e["titel"] for e in covers.refresh_targets(entries, infos)] == ["Keins", "Entfernt", "Neu"]
    assert [e["titel"] for e in covers.refresh_targets(entries, infos, only_missing=False)] == [
        "Gefunden", "Keins", "Entfernt", "Neu"]
