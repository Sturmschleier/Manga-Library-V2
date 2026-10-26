"""
device_sync.py
Geräte-Abgleich im WLAN - zwischen beliebigen Geräten mit der Bibliothek
(PC, Handy, Tablet). Aufgebaut wie der Sync der Anime-Liste.

Ein Gerät ist empfangsbereit, solange dort das Fenster „Geräte-Abgleich“
offen ist (kleiner HTTP-Server auf PORT). Das andere sucht es im WLAN
(oder bekommt die IP-Adresse eingetippt) und gleicht ab. Beim ersten Mal
werden die Geräte mit einem 6-stelligen Code gekoppelt; danach sind
Anfragen und Antworten mit dem dabei vereinbarten Schlüssel signiert
(HMAC-SHA256), andere Geräte im WLAN werden abgewiesen.

Ein Abgleich ist ein einziger Aufruf: Der Anfragende schickt seinen
gespeicherten Stand, das empfangsbereite Gerät führt ihn ein
(database.merge_sync, Regeln in sync_merge.py) und antwortet mit dem
gemeinsamen Stand, den der Anfragende ebenfalls einführt.

Abgeglichen wird nur die Datenbank (gespeicherte Einträge). Einstellungen
(config.json), Cover-Dateien und das Postfach-Passwort bleiben auf dem
jeweiligen Gerät; fehlende Cover sucht die Bibliothek nach dem Abgleich
selbst. Kennung, Name und gekoppelte Geräte stehen in SETTINGS_FILE neben
der Datenbank - bewusst nicht in der Datenbank, die per Google Drive auf
ein anderes Gerät wandern kann.
"""

import concurrent.futures
import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import sys
import threading
import time
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import database as db
from paths import base_dir, is_android

PORT = 47812            # die Anime-Liste nutzt 47811 - beide können gleichzeitig empfangen
APP = "mangalibv2"
PREFIX = "/mangalib"
SETTINGS_FILE = base_dir() / "sync_geraete.json"
CODE_SECONDS = 300      # so lange gilt ein angezeigter Kopplungscode
CODE_ATTEMPTS = 5       # danach wird der Code verworfen
MAX_SKEW = 300          # erlaubte Abweichung der Uhren in Sekunden
MAX_BODY = 20 * 1024 * 1024

_settings_lock = threading.Lock()
_merge_lock = threading.Lock()   # nie zwei Abgleiche gleichzeitig in dieselbe Datenbank


class SyncError(Exception):
    pass


class _HTTPServer(ThreadingHTTPServer):
    # Unter Windows erlaubt SO_REUSEADDR, denselben Port ein zweites Mal zu
    # belegen - Anfragen landeten dann zufällig bei einem der beiden.
    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True


# ------------------------------------------- Gerät und gekoppelte Geräte

def _load() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_FILE)


def _update(func: Callable[[dict], None]) -> dict:
    with _settings_lock:
        data = _load()
        func(data)
        _save(data)
        return data


def device_id() -> str:
    did = _load().get("device_id")
    if not did:
        def create(data):
            data.setdefault("device_id", uuid.uuid4().hex)
        did = _update(create)["device_id"]
    return did


def device_name() -> str:
    name = _load().get("device_name")
    if name:
        return name
    host = socket.gethostname()
    return f"Android-{device_id()[:4]}" if is_android() or host == "localhost" else host


def set_device_name(name: str) -> None:
    def change(data):
        data["device_name"] = (name or "").strip()[:60]
    _update(change)


def peers() -> dict:
    """Gekoppelte Geräte: {geräte_id: {"name", "key", "ip", "last_sync"}}."""
    found = _load().get("peers")
    return found if isinstance(found, dict) else {}


def _save_peer(pid: str, **fields) -> None:
    def change(data):
        all_ = data.get("peers") if isinstance(data.get("peers"), dict) else {}
        all_.setdefault(pid, {}).update(fields)
        data["peers"] = all_
    _update(change)


def remove_peer(pid: str) -> None:
    def change(data):
        (data.get("peers") or {}).pop(pid, None)
    _update(change)


def local_ip() -> str:
    """IP-Adresse dieses Geräts im WLAN (es wird dabei nichts gesendet)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def sign(key: str, ts: str, did: str, body: bytes) -> str:
    return hmac.new(bytes.fromhex(key), f"{ts}\n{did}\n".encode() + body, hashlib.sha256).hexdigest()


def _merge(state) -> dict:
    with _merge_lock:
        return db.merge_sync(state or {})


# ------------------------------------------------ Empfangsbereites Gerät

class Server:
    """Empfang für Kopplung und Abgleich. `on_change(event, info)` wird aus
    einem Hintergrund-Thread aufgerufen: ("paired", {"name"}) bzw.
    ("synced", {"name", "created", "updated", "deleted"})."""

    def __init__(self, on_change: Callable = lambda event, info: None):
        self.on_change = on_change
        self.httpd = None
        self.code = None
        self.code_until = 0.0
        self.code_attempts = 0
        self.lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self.httpd is not None

    def start(self, port: int = PORT) -> None:
        if self.httpd:
            return
        handler = type("Handler", (_Handler,), {"server_ref": self})
        try:
            self.httpd = _HTTPServer(("0.0.0.0", port), handler)
        except OSError as exc:
            raise SyncError(f"Empfang nicht möglich (Port {port} belegt?): {exc}") from exc
        threading.Thread(target=self.httpd.serve_forever, name="device-sync", daemon=True).start()

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else PORT

    def stop(self) -> None:
        httpd, self.httpd = self.httpd, None
        self.code = None
        if httpd:
            threading.Thread(target=lambda: (httpd.shutdown(), httpd.server_close()), daemon=True).start()

    def new_code(self) -> str:
        with self.lock:
            self.code = f"{secrets.randbelow(10**6):06d}"
            self.code_until = time.time() + CODE_SECONDS
            self.code_attempts = 0
            return self.code

    def check_code(self, code) -> bool:
        with self.lock:
            if not self.code or time.time() > self.code_until:
                self.code = None
                return False
            if hmac.compare_digest(str(code), self.code):
                self.code = None  # nur einmal verwendbar
                return True
            self.code_attempts += 1
            if self.code_attempts >= CODE_ATTEMPTS:
                self.code = None
            return False


class _Handler(BaseHTTPRequestHandler):
    server_ref: Server = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, code: int, data: dict, key: Optional[str] = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if key:  # Antwort ebenfalls signieren, damit der Anfragende ihr trauen kann
            ts = str(int(time.time()))
            self.send_header("X-Manga-Time", ts)
            self.send_header("X-Manga-Sig", sign(key, ts, device_id(), body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise SyncError("zu groß")
        return self.rfile.read(n)

    def do_GET(self):
        if self.path != f"{PREFIX}/hello":
            return self.reply(404, {"error": "unbekannt"})
        self.reply(200, {"app": APP, "id": device_id(), "name": device_name(),
                         "pairing": bool(self.server_ref.code)})

    def do_POST(self):
        try:
            body = self.read_body()
            if self.path == f"{PREFIX}/pair":
                return self.pair(json.loads(body))
            if self.path == f"{PREFIX}/sync":
                return self.sync(body)
            self.reply(404, {"error": "unbekannt"})
        except (SyncError, ValueError) as exc:
            self.reply(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - dem anfragenden Gerät die Ursache melden
            self.reply(500, {"error": f"Unerwarteter Fehler: {exc}"})

    def pair(self, data: dict):
        if not self.server_ref.check_code(data.get("code")):
            return self.reply(403, {"error": "Kopplungscode falsch oder abgelaufen"})
        pid, name = str(data.get("id") or ""), str(data.get("name") or "Gerät")[:60]
        if not pid:
            return self.reply(400, {"error": "Geräte-ID fehlt"})
        key = secrets.token_hex(32)
        _save_peer(pid, name=name, key=key, ip=self.client_address[0])
        self.server_ref.on_change("paired", {"name": name})
        self.reply(200, {"id": device_id(), "name": device_name(), "key": key})

    def sync(self, body: bytes):
        pid, ts, sig = (self.headers.get(h) or "" for h in ("X-Manga-Device", "X-Manga-Time", "X-Manga-Sig"))
        peer = peers().get(pid)
        if not peer:
            return self.reply(403, {"error": "Gerät ist nicht gekoppelt – bitte neu koppeln"})
        if not ts.isdigit() or abs(time.time() - int(ts)) > MAX_SKEW:
            return self.reply(403, {"error": "Uhrzeit der Geräte weicht zu stark ab"})
        if not hmac.compare_digest(sig, sign(peer["key"], ts, pid, body)):
            return self.reply(403, {"error": "Signatur ungültig – bitte neu koppeln"})
        data = json.loads(body)
        counts = _merge(data.get("state"))
        name = str(data.get("name") or peer.get("name") or "Gerät")[:60]
        _save_peer(pid, name=name, ip=self.client_address[0], last_sync=db.now_stamp())
        self.server_ref.on_change("synced", {"name": name, **counts})
        self.reply(200, {"state": db.sync_state(), "result": counts, "name": device_name()}, key=peer["key"])


# ------------------------------------------------- Anfragendes Gerät

def _request(ip: str, method: str, path: str, body=None, headers=None, timeout=30, port: int = PORT):
    con = http.client.HTTPConnection(ip, port, timeout=timeout)
    try:
        con.request(method, path, body=body, headers=headers or {})
        r = con.getresponse()
        data = r.read()
        return r.status, dict(r.getheaders()), data
    finally:
        con.close()


def hello(ip: str, timeout: float = 2, port: int = PORT) -> Optional[dict]:
    """Infos des Geräts unter ip oder None, wenn dort keine empfangsbereite
    Bibliothek läuft."""
    try:
        status, _, data = _request(ip, "GET", f"{PREFIX}/hello", timeout=timeout, port=port)
        info = json.loads(data)
    except (OSError, ValueError, http.client.HTTPException):
        return None
    if status != 200 or not isinstance(info, dict) or info.get("app") != APP or info.get("id") == device_id():
        return None
    return {**info, "ip": ip}


def scan() -> list:
    """Durchsucht das eigene WLAN (/24) nach empfangsbereiten Geräten."""
    own = local_ip()
    if own.startswith("127."):
        raise SyncError("Keine WLAN-Verbindung gefunden")
    prefix = own.rsplit(".", 1)[0]

    def probe(n):
        ip = f"{prefix}.{n}"
        if ip == own:
            return None
        try:
            socket.create_connection((ip, PORT), timeout=0.5).close()
        except OSError:
            return None
        return hello(ip)

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        found = [f for f in pool.map(probe, range(1, 255)) if f]
    return sorted(found, key=lambda f: str(f.get("name", "")).casefold())


def pair(ip: str, code: str, port: int = PORT) -> dict:
    """Koppelt mit dem Gerät unter ip. Liefert dessen Infos."""
    body = json.dumps({"id": device_id(), "name": device_name(), "code": (code or "").replace(" ", "")}).encode()
    try:
        status, _, data = _request(ip, "POST", f"{PREFIX}/pair", body, {"Content-Type": "application/json"},
                                   port=port)
        info = json.loads(data)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise SyncError(f"Gerät unter {ip} nicht erreichbar: {exc}") from exc
    if status != 200:
        raise SyncError(info.get("error") or f"Kopplung fehlgeschlagen ({status})")
    _save_peer(info["id"], name=info["name"], key=info["key"], ip=ip)
    return info


def find_peer(pid: str) -> str:
    """Aktuelle IP eines gekoppelten Geräts: zuerst die zuletzt bekannte,
    sonst im WLAN suchen."""
    known = peers().get(pid, {}).get("ip")
    if known:
        info = hello(known)
        if info and info["id"] == pid:
            return known
    for info in scan():
        if info["id"] == pid:
            return info["ip"]
    raise SyncError("Gerät nicht gefunden – ist dort „Geräte-Abgleich“ geöffnet und im selben WLAN?")


def sync_with(pid: str, ip: Optional[str] = None, port: int = PORT) -> dict:
    """Gleicht mit einem gekoppelten Gerät ab. Liefert {"received": Zähler
    für dieses Gerät, "sent": Zähler des anderen, "name"}."""
    peer = peers().get(pid)
    if not peer:
        raise SyncError("Gerät ist nicht gekoppelt")
    ip = ip or find_peer(pid)
    body = json.dumps({"name": device_name(), "state": db.sync_state()}, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    headers = {"Content-Type": "application/json", "X-Manga-Device": device_id(), "X-Manga-Time": ts,
               "X-Manga-Sig": sign(peer["key"], ts, device_id(), body)}
    try:
        status, rh, data = _request(ip, "POST", f"{PREFIX}/sync", body, headers, timeout=120, port=port)
        reply = json.loads(data)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise SyncError(f"Abgleich mit {peer.get('name')} fehlgeschlagen: {exc}") from exc
    if status != 200:
        raise SyncError(reply.get("error") or f"Abgleich fehlgeschlagen ({status})")
    rts = rh.get("X-Manga-Time", "")
    if not hmac.compare_digest(rh.get("X-Manga-Sig", ""), sign(peer["key"], rts, pid, data)):
        raise SyncError("Antwort des Geräts ist nicht korrekt signiert")
    counts = _merge(reply.get("state"))
    _save_peer(pid, name=reply.get("name") or peer.get("name"), ip=ip, last_sync=db.now_stamp())
    return {"received": counts, "sent": reply.get("result") or {}, "name": reply.get("name")}
