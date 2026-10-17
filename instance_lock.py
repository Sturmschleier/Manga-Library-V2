"""
instance_lock.py
Verhindert, dass das Programm zweimal gleichzeitig läuft: Beide Fenster
hätten sonst einen eigenen Zwischenspeicher, und wer zuletzt speichert,
würde die Änderungen des anderen still überschreiben.

Version 1 nutzte dafür QLockFile; ohne Qt übernimmt das eine Sperre des
Betriebssystems auf einer Datei neben der Datenbank. Sie verschwindet mit
dem Prozess von selbst - auch nach einem Absturz bleibt also keine
verwaiste Sperre zurück.
"""

import os
import sys
from typing import Optional


class InstanceLock:
    def __init__(self, path):
        self.path = str(path)
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        """True, wenn die Sperre gehalten wird (oder sich wegen eines anderen
        Problems, z.B. fehlender Schreibrechte, nicht prüfen lässt - das soll
        den Start nicht verhindern). False nur, wenn ein anderes laufendes
        Programmfenster sie hält."""
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        except PermissionError:
            return False   # Datei von einem anderen Prozess exklusiv geöffnet
        except OSError:
            return True
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass   # wird beim Schließen ohnehin freigegeben
        os.close(self._fd)
        self._fd = None
