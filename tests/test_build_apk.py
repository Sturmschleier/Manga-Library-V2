"""Tests für die Vorbereitung des Android-Builds (build_apk.py) - ohne
Flutter, nur der Zwischenordner und die Versionsnummer."""

import build_apk


def test_build_number_rises_with_version():
    assert build_apk.build_number("2.0.3") == 20003
    assert build_apk.build_number("2.1.0") > build_apk.build_number("2.0.99")


def test_stage_copies_only_program_code(tmp_path, monkeypatch):
    root = tmp_path / "projekt"
    (root / "ui").mkdir(parents=True)
    (root / "assets").mkdir()
    for name in ("main.py", "database.py", "build_exe.py", "drive_sync.py", "manga_library.db", "config.json",
                 "credentials.json", "pyproject.toml", "assets/MangaLibraryV2.png", "ui/app.py"):
        (root / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(build_apk, "ROOT", root)
    monkeypatch.setattr(build_apk, "SRC", root / ".apk-src")
    build_apk.stage()
    staged = sorted(p.relative_to(root / ".apk-src").as_posix() for p in (root / ".apk-src").rglob("*") if p.is_file())
    assert staged == ["assets/icon.png", "database.py", "main.py", "pyproject.toml", "ui/app.py"]
