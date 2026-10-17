"""
tests/test_instance_lock.py
Tests für instance_lock.py: nur ein Programmfenster gleichzeitig.
"""

import subprocess
import sys
from pathlib import Path

from instance_lock import InstanceLock

_HOLD_SCRIPT = """
import sys
sys.path.insert(0, sys.argv[1])
from instance_lock import InstanceLock
lock = InstanceLock(sys.argv[2])
print("ok" if lock.acquire() else "busy", flush=True)
sys.stdin.readline()
"""

ROOT = str(Path(__file__).resolve().parent.parent)


def _second_process_result(lock_file):
    """Versucht die Sperre in einem zweiten Prozess (wie ein zweites
    Programmfenster) und gibt "ok" oder "busy" zurück."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLD_SCRIPT, ROOT, str(lock_file)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        return proc.stdout.readline().strip()
    finally:
        proc.communicate("\n", timeout=10)


def test_second_process_is_refused_while_lock_is_held(tmp_path):
    lock_file = tmp_path / "db.lock"
    lock = InstanceLock(lock_file)
    assert lock.acquire()
    try:
        assert _second_process_result(lock_file) == "busy"
    finally:
        lock.release()


def test_lock_is_free_again_after_release(tmp_path):
    lock_file = tmp_path / "db.lock"
    lock = InstanceLock(lock_file)
    assert lock.acquire()
    lock.release()
    assert _second_process_result(lock_file) == "ok"


def test_release_without_acquire_is_harmless(tmp_path):
    InstanceLock(tmp_path / "db.lock").release()
