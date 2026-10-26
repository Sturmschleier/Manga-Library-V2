"""
sync_merge.py
Regeln für den Geräte-Abgleich (device_sync.py): führt zwei gespeicherte
Stände zusammen - ohne Datenbank und Netzwerk, damit sie sich direkt
testen lassen.

Ein Stand ist {"entries": [Einträge], "deleted": {uid: Löschzeitpunkt}}
(siehe database.sync_state). Jeder Eintrag hat eine feste Kennung (uid)
und den Zeitpunkt seiner letzten Änderung (geaendert, UTC als Text).

- Pro Eintrag (gleiche uid) gilt die zuletzt geänderte Fassung.
- Ein Löschvermerk gewinnt gegen jede Fassung, die nicht neuer ist; wurde
  der Eintrag nach dem Löschen woanders noch geändert, bleibt er.
- Zwei Einträge mit demselben Titel (ohne Groß-/Kleinschreibung) sind
  dasselbe Werk, auch mit verschiedener uid - etwa wenn auf beiden Geräten
  dieselbe Sammlung importiert wurde. Es bleibt die zuletzt geänderte
  Fassung, die andere bekommt einen Löschvermerk.

Das Ergebnis hängt nicht davon ab, welches Gerät welche Seite ist - beide
Geräte kommen so zum selben Stand.
"""

from dataclasses import dataclass, field
from typing import Optional

import database as db


@dataclass
class MergeResult:
    entries: list                                  # zusammengeführte Einträge
    deleted: dict                                  # alle Löschvermerke {uid: Zeitpunkt}
    counts: dict = field(default_factory=dict)     # gegenüber dem lokalen Stand: created, updated, deleted
    changed: bool = False                          # weicht vom lokalen Stand ab (Einträge oder Vermerke)?


def _clean_entry(raw) -> Optional[dict]:
    """Nur bekannte Felder als Text; ohne uid oder Änderungszeit None."""
    if not isinstance(raw, dict):
        return None
    entry = {c: raw.get(c) if isinstance(raw.get(c), str) else "" for c in db.STORED_COLUMN_NAMES}
    if not entry["uid"] or not entry["geaendert"]:
        return None
    return entry


def _clean_state(state) -> tuple[list, dict]:
    state = state if isinstance(state, dict) else {}
    entries = [e for e in map(_clean_entry, state.get("entries") or []) if e is not None]
    raw_deleted = state.get("deleted") if isinstance(state.get("deleted"), dict) else {}
    deleted = {uid: at for uid, at in raw_deleted.items() if isinstance(uid, str) and uid and isinstance(at, str)}
    return entries, deleted


def _rank(entry: dict) -> tuple:
    """Reihenfolge "neuer": Änderungszeit, bei Gleichstand fest nach Inhalt
    - damit beide Geräte dieselbe Fassung wählen."""
    return entry["geaendert"], [entry[c] for c in db.STORED_COLUMN_NAMES]


def _title_key(entry: dict) -> str:
    return (entry.get("titel") or "").strip().casefold()


def _content(entry: dict) -> list:
    return [entry[c] for c in db.STORED_COLUMN_NAMES]


def merge(local: dict, remote: dict) -> MergeResult:
    local_entries, local_deleted = _clean_state(local)
    remote_entries, remote_deleted = _clean_state(remote)

    deleted = dict(local_deleted)
    for uid, at in remote_deleted.items():
        if at > deleted.get(uid, ""):
            deleted[uid] = at

    by_uid = {}
    for entry in local_entries + remote_entries:
        current = by_uid.get(entry["uid"])
        if current is None or _rank(entry) > _rank(current):
            by_uid[entry["uid"]] = entry

    for uid, entry in list(by_uid.items()):
        if deleted.get(uid, "") >= entry["geaendert"]:
            del by_uid[uid]
        else:
            deleted.pop(uid, None)   # nach dem Löschen noch geändert: der Eintrag bleibt

    by_title = {}
    for entry in by_uid.values():
        key = _title_key(entry)
        if key:
            by_title.setdefault(key, []).append(entry)
    for group in by_title.values():
        if len(group) < 2:
            continue
        winner = max(group, key=_rank)
        for loser in group:
            if loser is not winner:
                del by_uid[loser["uid"]]
                deleted[loser["uid"]] = max(deleted.get(loser["uid"], ""), winner["geaendert"])

    local_by_uid = {e["uid"]: e for e in local_entries}
    counts = {
        "created": sum(uid not in local_by_uid for uid in by_uid),
        "updated": sum(uid in local_by_uid and _content(local_by_uid[uid]) != _content(e) for uid, e in by_uid.items()),
        "deleted": sum(uid not in by_uid for uid in local_by_uid),
    }
    changed = any(counts.values()) or deleted != local_deleted or len(local_by_uid) != len(local_entries)
    return MergeResult(entries=list(by_uid.values()), deleted=deleted, counts=counts, changed=changed)
