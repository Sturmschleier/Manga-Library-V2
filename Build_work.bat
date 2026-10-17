@echo off
REM Build_work.bat
REM Baut die exe ueber build.bat (gleiche Bauanleitung build_exe.py und
REM gleiche festgelegte Versionen) und kopiert die fertige MangaLibraryV2.exe
REM anschliessend nach ..\WorkV2, wo sie eine vorhandene Datei ersetzt.
REM Die Arbeitsdaten dort (manga_library.db, config.json, covers,
REM credentials.json, token.json, LOG, BACKUP) bleiben unberuehrt.
REM Vorher MangaLibraryV2.exe in ..\WorkV2 beenden, sonst kann sie nicht
REM ersetzt werden.

cd /d "%~dp0"

if not exist "..\WorkV2" (
    echo.
    echo FEHLER: Zielordner ..\WorkV2 existiert nicht: %~dp0..\WorkV2
    pause
    exit /b 1
)

call build.bat --no-pause
if errorlevel 1 (
    echo.
    echo FEHLER: Build fehlgeschlagen - die exe in ..\WorkV2 wurde nicht veraendert.
    pause
    exit /b 1
)

copy /Y "dist\MangaLibraryV2.exe" "..\WorkV2\MangaLibraryV2.exe" >nul
if errorlevel 1 (
    echo.
    echo FEHLER: Die exe konnte nicht nach ..\WorkV2 kopiert werden.
    echo Laeuft MangaLibraryV2.exe dort noch? Bitte beenden und erneut starten.
    pause
    exit /b 1
)

echo.
echo Fertig! MangaLibraryV2.exe wurde nach ..\WorkV2 kopiert.
pause
