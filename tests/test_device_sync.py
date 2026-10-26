"""Tests für den Geräte-Abgleich im WLAN (device_sync.py) - Kopplung und
Abgleich laufen über einen echten Server auf 127.0.0.1."""

import pytest

import config
import covers
import database as db
import device_sync


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_FILE", tmp_path / "manga_library.db")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(device_sync, "SETTINGS_FILE", tmp_path / "sync_geraete.json")
    monkeypatch.setattr(covers, "COVER_DIR", tmp_path / "covers")
    db.init_db()
    server = device_sync.Server()
    server.start(port=0)   # freier Port
    yield server
    server.stop()


def test_device_id_is_stable_and_name_editable(env):
    assert device_sync.device_id() == device_sync.device_id()
    device_sync.set_device_name("  Mein PC  ")
    assert device_sync.device_name() == "Mein PC"


def test_pair_with_wrong_code_fails(env):
    env.new_code()
    with pytest.raises(device_sync.SyncError, match="falsch"):
        device_sync.pair("127.0.0.1", "000000" if env.code != "000000" else "111111", port=env.port)


def test_code_is_dropped_after_too_many_attempts(env):
    code = env.new_code()
    for _ in range(device_sync.CODE_ATTEMPTS):
        assert not env.check_code("x")
    assert not env.check_code(code)


def test_pair_and_sync_roundtrip(env):
    # Beide "Geräte" laufen hier im selben Prozess mit derselben Kennung und
    # Einstellungsdatei - das genügt, um Kopplung, Signaturen und Abgleich
    # über die echte HTTP-Verbindung durchzuspielen.
    events = []
    env.on_change = lambda event, info: events.append(event)
    own = device_sync.device_id()
    code = env.new_code()
    info = device_sync.pair("127.0.0.1", f"{code[:3]} {code[3:]}", port=env.port)
    assert info["id"] == own
    assert events == ["paired"]

    db.replace_all([{"titel": "Berserk"}])
    result = device_sync.sync_with(own, "127.0.0.1", port=env.port)
    assert events == ["paired", "synced", "covers"]
    assert result["received"] == {"created": 0, "updated": 0, "deleted": 0, "covers": 0}
    assert device_sync.peers()[own]["last_sync"]


def test_hello_ignores_own_device(env):
    assert device_sync.hello("127.0.0.1", port=env.port) is None


def test_sync_from_unpaired_device_is_rejected(env):
    import json
    import time

    body = json.dumps({"state": {}}).encode()
    status, _, data = device_sync._request(
        "127.0.0.1", "POST", f"{device_sync.PREFIX}/sync", body,
        {"X-Manga-Device": "fremd", "X-Manga-Time": str(int(time.time())), "X-Manga-Sig": "x"}, port=env.port)
    assert status == 403
    assert "nicht gekoppelt" in json.loads(data)["error"]


def test_cover_upload_must_be_requested(env):
    import hashlib
    import json

    own = device_sync.device_id()
    code = env.new_code()
    device_sync.pair("127.0.0.1", code, port=env.port)
    peer = device_sync.peers()[own]
    con = device_sync._Connection(own, peer, "127.0.0.1", env.port)
    data = b"x" * 2000
    with pytest.raises(device_sync.SyncError, match="nicht angefordert"):
        con.call("cover-put", data, {"Content-Type": "application/octet-stream", "X-Manga-File": "a.jpg",
                                     "X-Manga-Sha": hashlib.sha1(data).hexdigest()})
    assert not (covers.COVER_DIR / "a.jpg").exists()
    assert json.loads(con.call("covers-done", b"{}")) == {"covers": 0}
