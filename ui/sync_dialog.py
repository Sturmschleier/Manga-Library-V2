"""
ui/sync_dialog.py
Fenster "Geräte-Abgleich" (device_sync.py) - wie der Tab "Sync" der
Anime-Liste: Solange es offen ist, ist dieses Gerät im WLAN
empfangsbereit. Von hier aus wird gekoppelt (6-stelliger Code) und mit
gekoppelten Geräten abgeglichen.

Abgeglichen wird der gespeicherte Stand. Ungespeicherte Änderungen müssen
deshalb vorher gespeichert werden (ui.app.MangaApp.open_device_sync fragt
nach); nach jedem Abgleich lädt das Hauptfenster die Datenbank neu.
"""

from datetime import datetime

import flet as ft

import device_sync
from ui.common import close_dialog, on_ui, run_background
from ui.theme import P


def _when(stamp: str) -> str:
    if not stamp:
        return "noch nie abgeglichen"
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return ""
    return f"zuletzt {moment:%d.%m.%Y %H:%M}"


def summary(counts: dict) -> str:
    parts = [f"{counts.get('created', 0)} neu", f"{counts.get('updated', 0)} geändert"]
    if counts.get("deleted"):
        parts.append(f"{counts['deleted']} gelöscht")
    if counts.get("covers"):
        parts.append(f"{counts['covers']} Cover")
    return ", ".join(parts)


class SyncDialog:
    def __init__(self, app, mobile: bool = False):
        self.app = app
        self.page = app.page
        # Eine laufende Cover-Suche könnte gleich übertragene Cover wieder
        # überschreiben; reload_after_sync startet sie danach neu
        app.cancel_cover_job()
        self.server = device_sync.Server(lambda event, info: on_ui(self.page, self._on_remote, event, info))
        muted = P.text_muted

        self.name_field = ft.TextField(label="Name dieses Geräts", value=device_sync.device_name(), dense=True,
                                       on_blur=self._save_name, on_submit=self._save_name)
        self.address = ft.Text(size=12, color=muted, selectable=True)
        self.code_text = ft.Text(size=30, weight=ft.FontWeight.BOLD, selectable=True, visible=False)
        self.code_hint = ft.Text("Diesen Code auf dem anderen Gerät eingeben (5 Minuten gültig).",
                                 size=12, color=muted, visible=False)
        self.status_text = ft.Text(selectable=True, expand=True)
        self.status_ring = ft.ProgressRing(width=18, height=18, stroke_width=2)
        self.status_box = ft.Container(
            ft.Row([self.status_ring, self.status_text], spacing=10),
            border=ft.Border.all(1, P.border), border_radius=8, padding=10, visible=False,
        )
        self.peer_list = ft.Column(spacing=6)
        self.found_list = ft.Column(spacing=6)
        self.ip_field = ft.TextField(label="IP-Adresse", hint_text="z. B. 192.168.1.23", dense=True, expand=True,
                                     keyboard_type=ft.KeyboardType.NUMBER, on_submit=self._connect_ip)
        self.pair_target = None
        self.pair_title = ft.Text(weight=ft.FontWeight.W_600)
        self.code_field = ft.TextField(label="Kopplungscode", dense=True, expand=True, max_length=7,
                                       keyboard_type=ft.KeyboardType.NUMBER, on_submit=self._pair)
        self.pair_box = ft.Column([
            self.pair_title,
            ft.Text("Auf dem anderen Gerät unter „Geräte-Abgleich“ auf „Kopplungscode anzeigen“ tippen und "
                    "den Code hier eingeben.", size=12, color=muted),
            ft.Row([self.code_field, ft.FilledButton("Koppeln", icon=ft.Icons.LINK, on_click=self._pair)]),
        ], spacing=6, visible=False)
        self.buttons = []

        def btn(text, handler, icon, filled=False):
            b = (ft.FilledButton if filled else ft.OutlinedButton)(text, icon=icon, on_click=handler)
            self.buttons.append(b)
            return b

        def heading(text):
            return ft.Text(text, size=15, weight=ft.FontWeight.BOLD)

        content = ft.Column([
            self.status_box,
            heading("Dieses Gerät"),
            self.name_field,
            self.address,
            ft.Text("Empfangsbereit, solange dieses Fenster geöffnet ist.", size=12, color=muted),
            ft.Row([ft.OutlinedButton("Kopplungscode anzeigen", icon=ft.Icons.PIN, on_click=self._show_code)]),
            self.code_text,
            self.code_hint,
            ft.Divider(),
            heading("Gekoppelte Geräte"),
            self.peer_list,
            ft.Text("Auf dem anderen Gerät muss dafür ebenfalls „Geräte-Abgleich“ geöffnet sein.",
                    size=12, color=muted),
            ft.Divider(),
            heading("Geräte suchen"),
            ft.Row([btn("Im WLAN suchen", self._scan, ft.Icons.WIFI_FIND, True)]),
            self.found_list,
            ft.Text("Nicht gefunden? IP-Adresse des anderen Geräts eingeben (steht dort unter „Dieses Gerät“).",
                    size=12, color=muted),
            ft.Row([self.ip_field, btn("Verbinden", self._connect_ip, ft.Icons.LINK)]),
            self.pair_box,
            ft.Divider(),
            ft.Text("Pro Eintrag gilt die zuletzt gespeicherte Fassung; Löschungen werden übernommen. Einträge "
                    "mit gleichem Titel werden zusammengelegt. Vor jeder Änderung wird die Datenbank nach "
                    "BACKUP/ gesichert. Einstellungen, eigene Cover und Passwörter bleiben auf dem Gerät.",
                    size=12, color=muted),
        ], spacing=8, tight=True, scroll=ft.ScrollMode.AUTO)

        self.dialog = ft.AlertDialog(
            modal=True, title=ft.Text("Geräte-Abgleich"),
            content=ft.Container(content, width=None if mobile else 560),
            actions=[ft.FilledButton("Schließen", on_click=self._close)],
            on_dismiss=lambda _e: self.server.stop(),
        )
        self._start_server()
        self._render_peers()
        self.page.show_dialog(self.dialog)

    # --------------------------------------------------------------- Empfang

    def _start_server(self):
        try:
            self.server.start()
            self.address.value = f"Adresse im WLAN: {device_sync.local_ip()}"
        except device_sync.SyncError as exc:
            self.address.value = str(exc)

    def _close(self, _e=None):
        self._save_name()
        self.server.stop()
        close_dialog(self.page)

    def _on_remote(self, event: str, info: dict):
        if event == "paired":
            self.code_text.visible = self.code_hint.visible = False
            self._status(f"Gekoppelt mit {info.get('name')}.", running=False)
        elif event == "synced":
            self.app.reload_after_sync(info.get("name"), info)
            self._status(f"{info.get('name')} gleicht ab: {summary(info)}. Cover folgen …")
        elif event == "covers":
            self.app.reload_after_sync(info.get("name"), info)
            self._status(f"{info.get('name')} hat abgeglichen (Cover: {info.get('covers', 0)} geändert).",
                         running=False)
        self._render_peers()
        self.page.update()

    def _save_name(self, _e=None):
        device_sync.set_device_name(self.name_field.value or "")
        self.name_field.value = device_sync.device_name()
        self.page.update()

    def _show_code(self, _e=None):
        if not self.server.running:
            self._status("Empfang ist nicht aktiv – siehe Hinweis unter „Dieses Gerät“.", running=False)
            return
        code = self.server.new_code()
        self.code_text.value = f"{code[:3]} {code[3:]}"
        self.code_text.visible = self.code_hint.visible = True
        self.page.update()

    # ------------------------------------------------------------- Anzeige

    def _status(self, text: str, running: bool = True):
        self.status_box.visible = True
        self.status_text.value = text
        self.status_ring.visible = running
        for b in self.buttons:
            b.disabled = running
        self.page.update()

    def _device_row(self, name: str, detail: str, action: ft.Control, extra=None) -> ft.Control:
        return ft.Row([
            ft.Icon(ft.Icons.DEVICES),
            ft.Column([ft.Text(name, weight=ft.FontWeight.W_600),
                       ft.Text(detail, size=12, color=P.text_muted)], spacing=0, expand=True),
            action,
            *([extra] if extra else []),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _sync_button(self, pid: str, ip=None) -> ft.Control:
        b = ft.FilledButton("Abgleichen", icon=ft.Icons.SYNC, on_click=lambda _e: self._sync(pid, ip))
        self.buttons.append(b)
        return b

    def _render_peers(self):
        rows = []
        for pid, peer in sorted(device_sync.peers().items(), key=lambda kv: str(kv[1].get("name", "")).casefold()):
            rows.append(self._device_row(
                peer.get("name") or "Gerät", _when(peer.get("last_sync") or ""), self._sync_button(pid),
                ft.IconButton(ft.Icons.LINK_OFF, tooltip="Kopplung entfernen",
                              on_click=lambda _e, p=pid: self._unpair(p)),
            ))
        self.peer_list.controls = rows or [ft.Text("Noch keine Geräte gekoppelt.", size=12, color=P.text_muted)]

    def _unpair(self, pid: str):
        device_sync.remove_peer(pid)
        self._render_peers()
        self.page.update()

    # ------------------------------------------------------------ Aktionen

    def _scan(self, _e=None):
        self._status("Suche Geräte im WLAN …")

        def done(found, error):
            if error is not None:
                self._status(str(error), running=False)
                return
            known = device_sync.peers()
            self.found_list.controls = [
                self._device_row(f["name"], f["ip"], self._sync_button(f["id"], f["ip"]) if f["id"] in known else
                                 ft.OutlinedButton("Koppeln", icon=ft.Icons.PIN,
                                                   on_click=lambda _e, f=f: self._ask_code(f["ip"], f["name"])))
                for f in found
            ]
            self._status(f"{len(found)} Gerät(e) gefunden." if found else
                         "Kein Gerät gefunden – ist dort „Geräte-Abgleich“ geöffnet und im selben WLAN?",
                         running=False)

        run_background(self.page, device_sync.scan, done)

    def _connect_ip(self, _e=None):
        ip = (self.ip_field.value or "").strip()
        if not ip:
            self._status("Bitte die IP-Adresse eingeben.", running=False)
            return
        self._status(f"Verbinde mit {ip} …")

        def done(info, error):
            if error is not None or not info:
                self._status(f"Unter {ip} ist keine empfangsbereite Bibliothek erreichbar.", running=False)
                return
            if info["id"] in device_sync.peers():
                self._sync(info["id"], ip)
            else:
                self._status(f"Gefunden: {info['name']}", running=False)
                self._ask_code(ip, info["name"])

        run_background(self.page, lambda: device_sync.hello(ip), done)

    def _ask_code(self, ip: str, name: str):
        self.pair_target = (ip, name)
        self.pair_title.value = f"Mit „{name}“ koppeln"
        self.code_field.value = ""
        self.pair_box.visible = True
        self.page.update()

    def _pair(self, _e=None):
        if not self.pair_target:
            return
        ip, name = self.pair_target
        code = self.code_field.value or ""
        self.pair_box.visible = False
        self._status(f"Kopple mit {name} …")

        def done(info, error):
            if error is not None:
                self._status(str(error), running=False)
                return
            self._render_peers()
            self._sync(info["id"], ip)

        run_background(self.page, lambda: device_sync.pair(ip, code), done)

    def _sync(self, pid: str, ip=None):
        name = device_sync.peers().get(pid, {}).get("name") or "Gerät"
        self._status(f"Gleiche mit {name} ab …")

        def done(result, error):
            if error is not None:
                self._status(str(error), running=False)
                return
            self.app.reload_after_sync(result.get("name") or name, result["received"])
            self._render_peers()
            self._status(f"Abgeglichen mit {result.get('name') or name}.\n"
                         f"Hier: {summary(result['received'])}. Dort: {summary(result['sent'])}.", running=False)

        def progress(text):
            on_ui(self.page, self._status, text)

        run_background(self.page, lambda: device_sync.sync_with(pid, ip, progress=progress), done)
