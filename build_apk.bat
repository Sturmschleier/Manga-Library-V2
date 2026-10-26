@echo off
REM build_apk.bat
REM Baut die Android-App MangaLibraryV2.apk mit "flet build apk":
REM   - in derselben Build-Umgebung .venv-build wie build.bat (feste
REM     Versionen aus requirements-build.txt)
REM   - nach build_apk.py (dort steht, was in die APK kommt und wohin
REM     Flutter, JDK und Android SDK geladen werden)
REM
REM Aufruf:   build_apk.bat              wartet am Ende auf einen Tastendruck
REM           build_apk.bat --no-pause   z.B. aus einem anderen Skript heraus
REM Ergebnis: dist\MangaLibraryV2.apk
REM
REM Voraussetzung: Windows-Entwicklermodus (Einstellungen > System > Fuer
REM Entwickler). Der erste Build laedt mehrere GB und dauert entsprechend.

setlocal
cd /d "%~dp0"
set "VENV=.venv-build"

if exist "%VENV%\Scripts\python.exe" goto :venv_vorhanden
call :suche_python || goto :fehler
echo Lege die Build-Umgebung %VENV% an ...
%PY% -m venv "%VENV%" || goto :fehler
:venv_vorhanden

echo Installiere die festgelegten Versionen aus requirements-build.txt ...
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r requirements-build.txt || goto :fehler

"%VENV%\Scripts\python.exe" build_apk.py || goto :fehler

echo.
echo Fertig! dist\MangaLibraryV2.apk aufs Handy kopieren und dort oeffnen
echo (Installation aus unbekannten Quellen erlauben). Die App legt ihre Daten
echo in ihrem eigenen Ordner ab - die Sammlung kommt per Geraete-Abgleich drauf.
if /i not "%~1"=="--no-pause" pause
exit /b 0

:suche_python
set "PY="
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=py -3"
)
if defined PY exit /b 0
echo.
echo FEHLER: Python 3.10 oder neuer ist nicht installiert (oder nicht im PATH).
exit /b 1

:fehler
echo.
echo FEHLER: Der Build ist fehlgeschlagen (siehe Meldungen oben).
if /i not "%~1"=="--no-pause" pause
exit /b 1
