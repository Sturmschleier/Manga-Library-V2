"""Tests für die Regeln des Geräte-Abgleichs (sync_merge.py) und die
Kennungen/Löschvermerke in database.py."""

import pytest

import config
import database as db
import sync_merge


def entry(uid, titel, geaendert, **values):
    e = dict.fromkeys(db.STORED_COLUMN_NAMES, "")
    e.update(uid=uid, titel=titel, geaendert=geaendert, **values)
    return e


def state(*entries, deleted=None):
    return {"entries": list(entries), "deleted": dict(deleted or {})}


def titles(result):
    return sorted(e["titel"] for e in result.entries)


def test_newer_version_wins_per_uid():
    local = state(entry("a", "Berserk", "2026-01-01", baende_bis="3"))
    remote = state(entry("a", "Berserk", "2026-02-01", baende_bis="5"))
    result = sync_merge.merge(local, remote)
    assert [e["baende_bis"] for e in result.entries] == ["5"]
    assert result.counts == {"created": 0, "updated": 1, "deleted": 0}
    assert result.changed


def test_new_entries_of_both_sides_are_kept():
    local = state(entry("a", "Berserk", "2026-01-01"))
    remote = state(entry("b", "Vinland Saga", "2026-01-01"))
    result = sync_merge.merge(local, remote)
    assert titles(result) == ["Berserk", "Vinland Saga"]
    assert result.counts["created"] == 1


def test_deletion_wins_over_older_version():
    local = state(entry("a", "Berserk", "2026-01-01"))
    remote = state(deleted={"a": "2026-01-02"})
    result = sync_merge.merge(local, remote)
    assert result.entries == []
    assert result.deleted == {"a": "2026-01-02"}
    assert result.counts["deleted"] == 1


def test_change_after_deletion_keeps_entry():
    local = state(entry("a", "Berserk", "2026-01-03"))
    remote = state(deleted={"a": "2026-01-02"})
    result = sync_merge.merge(local, remote)
    assert titles(result) == ["Berserk"]
    assert result.deleted == {}


def test_same_title_different_uid_is_merged_into_newer():
    local = state(entry("a", "Berserk", "2026-01-01", baende_bis="3"))
    remote = state(entry("b", " berserk ", "2026-01-05", baende_bis="4"))
    result = sync_merge.merge(local, remote)
    assert [(e["uid"], e["baende_bis"]) for e in result.entries] == [("b", "4")]
    assert result.deleted == {"a": "2026-01-05"}


def test_merge_is_symmetric():
    a = state(entry("a", "Berserk", "2026-01-01"), entry("c", "Monster", "2026-01-04", baende_bis="2"),
              deleted={"x": "2026-01-01"})
    b = state(entry("b", "Berserk", "2026-01-02"), entry("c", "Monster", "2026-01-04", baende_bis="9"),
              entry("x", "Gelöscht?", "2026-01-03"))
    ab, ba = sync_merge.merge(a, b), sync_merge.merge(b, a)
    key = lambda r: sorted(r.entries, key=lambda e: e["uid"])  # noqa: E731
    assert key(ab) == key(ba)
    assert ab.deleted == ba.deleted


def test_identical_states_change_nothing():
    s = state(entry("a", "Berserk", "2026-01-01"), deleted={"z": "2026-01-01"})
    result = sync_merge.merge(s, s)
    assert not result.changed
    assert result.counts == {"created": 0, "updated": 0, "deleted": 0}


def test_invalid_remote_data_is_ignored():
    local = state(entry("a", "Berserk", "2026-01-01"))
    remote = {"entries": [{"titel": "ohne uid"}, "Unsinn", {"uid": "b", "titel": "ohne Zeit"}],
              "deleted": {"": "x", "q": 5}}
    result = sync_merge.merge(local, remote)
    assert titles(result) == ["Berserk"]
    assert not result.changed


# ------------------------------------------------------------- Datenbank

@pytest.fixture
def db_env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_FILE", tmp_path / "manga_library.db")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    db.init_db()


def test_replace_all_assigns_uid_and_stamps_only_changed_entries(db_env):
    saved = db.replace_all([{"titel": "A"}, {"titel": "B"}])
    assert all(e["uid"] and e["geaendert"] for e in saved)
    stamps = {e["titel"]: e["geaendert"] for e in saved}
    changed = [dict(e, baende_bis="2") if e["titel"] == "A" else e for e in saved]
    again = {e["titel"]: e["geaendert"] for e in db.replace_all(changed)}
    assert again["A"] > stamps["A"]
    assert again["B"] == stamps["B"]


def test_replace_all_records_deletions_and_undo_removes_them(db_env):
    saved = db.replace_all([{"titel": "A"}, {"titel": "B"}])
    a = next(e for e in saved if e["titel"] == "A")
    db.replace_all([e for e in saved if e["titel"] != "A"])
    assert set(db.sync_state()["deleted"]) == {a["uid"]}
    db.replace_all([*db.load_all(), a])   # Rückgängig nach dem Speichern
    assert db.sync_state()["deleted"] == {}


def test_replace_all_gives_duplicate_uid_a_new_one(db_env):
    saved = db.replace_all([{"titel": "A"}])
    twice = db.replace_all([saved[0], dict(saved[0], titel="Kopie")])
    assert len({e["uid"] for e in twice}) == 2


def test_merge_sync_writes_result_and_backs_up(db_env):
    db.replace_all([{"titel": "Lokal"}])
    remote = state(entry("r1", "Vom Handy", "2030-01-01", baende_bis="7"))
    counts = db.merge_sync(remote)
    assert counts["created"] == 1
    assert sorted(e["titel"] for e in db.load_all()) == ["Lokal", "Vom Handy"]
    assert any(p.name.endswith("_vor-sync.db") for p in db.backup_dir().iterdir())


def test_init_db_fills_missing_uids(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setattr(db, "DB_FILE", tmp_path / "manga_library.db")
    conn = sqlite3.connect(db.DB_FILE)
    conn.execute("CREATE TABLE werke (id INTEGER PRIMARY KEY AUTOINCREMENT, titel TEXT)")
    conn.execute("INSERT INTO werke (titel) VALUES ('Alt')")
    conn.commit()
    conn.close()
    db.init_db()
    (row,) = db.load_all()
    assert row["uid"] and row["geaendert"]


# ------------------------------------------------------------------ Cover

def cover(titel, quelle, geaendert, datei="", manuell=False, sha=""):
    return {"titel": titel, "isbn": "", "datei": datei, "quelle": quelle, "geprueft_am": "2026-01-01",
            "geaendert": geaendert, "manuell": manuell, "sha": sha}


def test_cover_manual_choice_beats_newer_automatic_one():
    import covers

    pc = [cover("A", covers.QUELLE_EIGEN, "2025-01-01", "eigen_a.jpg", manuell=True, sha="1" * 40)]
    handy = [cover("A", covers.QUELLE_DNB, "2026-10-01", "123.jpg", sha="2" * 40)]
    merged, changed = covers.merge_states(handy, pc)
    assert merged["A"]["datei"] == "eigen_a.jpg"
    assert changed == ["A"]
    assert covers.merge_states(pc, handy)[0]["A"]["datei"] == "eigen_a.jpg"


def test_cover_result_beats_nothing_found_and_newer_wins_otherwise():
    import covers

    found = cover("A", covers.QUELLE_DNB, "2026-01-01", "1.jpg")
    nothing = cover("A", covers.QUELLE_KEINE, "2026-05-01")
    assert covers.merge_states([nothing], [found])[0]["A"]["quelle"] == covers.QUELLE_DNB
    newer = cover("A", covers.QUELLE_VLB, "2026-06-01", "1.jpg")
    assert covers.merge_states([found], [newer])[0]["A"]["quelle"] == covers.QUELLE_VLB


def test_cover_same_entry_prefers_side_with_file():
    import covers

    with_file = cover("A", covers.QUELLE_DNB, "2026-01-01", "1.jpg", sha="a" * 40)
    without = cover("A", covers.QUELLE_DNB, "2026-01-01", "1.jpg")
    merged, changed = covers.merge_states([without], [with_file])
    assert merged["A"]["sha"] == "a" * 40
    assert changed == []   # der Eintrag selbst ist gleich - nur die Datei fehlt


def test_cover_unsafe_file_names_are_rejected():
    import covers

    assert not covers.safe_file_name("../config.json")
    assert not covers.safe_file_name("..\\x.jpg")
    assert not covers.safe_file_name("x.exe")
    assert covers.safe_file_name("eigen_0123abcd.png")
    evil = cover("A", covers.QUELLE_EIGEN, "2030-01-01", "../evil.jpg", manuell=True)
    assert covers.merge_states([], [evil]) == ({}, [])


def test_cover_store_file_checks_hash(tmp_path, monkeypatch):
    import hashlib

    import covers

    monkeypatch.setattr(covers, "COVER_DIR", tmp_path)
    data = b"bild" * 500
    with pytest.raises(ValueError):
        covers.store_file("1.jpg", data, "0" * 40)
    covers.store_file("1.jpg", data, hashlib.sha1(data).hexdigest())
    assert covers.file_hashes() == {"1.jpg": hashlib.sha1(data).hexdigest()}
    assert covers.wanted_files({"A": cover("A", covers.QUELLE_DNB, "x", "1.jpg", sha="f" * 40)}) == {"1.jpg": "f" * 40}


def test_cover_table_gets_sync_columns_and_marks_manual(db_env):
    import covers

    with db.get_connection() as conn:
        conn.execute("CREATE TABLE covers (titel TEXT PRIMARY KEY, isbn TEXT, datei TEXT, quelle TEXT, "
                     "geprueft_am TEXT)")
        conn.execute("INSERT INTO covers VALUES ('Eigen', '', 'e.jpg', 'eigen', '2025-01-01')")
        conn.execute("INSERT INTO covers VALUES ('Auto', '1', '1.jpg', 'dnb', '2025-01-01')")
    covers.ensure_table()
    infos = covers.load_all()
    assert infos["Eigen"].manuell and not infos["Auto"].manuell
    saved = covers.save(covers.CoverInfo("Neu", quelle=covers.QUELLE_KEINE))
    assert saved.geaendert
