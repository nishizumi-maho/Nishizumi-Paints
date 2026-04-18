@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo =========================================
echo Nishizumi Paints - DIR No-Browser Build
echo =========================================
echo.

set "SCRIPT=Nishizumi_Paintsv6_nobrowser.py"

if not exist "%SCRIPT%" (
    echo [ERROR] %SCRIPT% was not found in this folder.
    echo.
    pause
    exit /b 1
)

echo [INFO] Using script: %SCRIPT%

echo [INFO] Installing/updating build dependencies...
py -m pip install --upgrade pyinstaller requests pyyaml beautifulsoup4 pyirsdk
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install/update build dependencies.
    pause
    exit /b 1
)

if exist "build" (
    echo [INFO] Cleaning previous build folder...
    rmdir /s /q "build"
)

if exist "dist\NishizumiPaints" (
    echo [INFO] Cleaning previous dist\NishizumiPaints folder...
    rmdir /s /q "dist\NishizumiPaints"
)

if exist "dist\NishizumiPaints.exe" (
    echo [INFO] Removing previous onefile dist\NishizumiPaints.exe...
    del /f /q "dist\NishizumiPaints.exe"
)

set "CMD=py -m PyInstaller --noconfirm --clean --onedir --windowed --name NishizumiPaints"

if exist "nishizumi_paints_icon.ico" (
    set "CMD=!CMD! --icon nishizumi_paints_icon.ico"
)
if exist "nishizumi_paints_icon.png" (
    set "CMD=!CMD! --add-data nishizumi_paints_icon.png;."
)
if exist "nishizumi_paints_icon.ico" (
    set "CMD=!CMD! --add-data nishizumi_paints_icon.ico;."
)
if exist "tp_showroom_mapping.seed.json" (
    set "CMD=!CMD! --add-data tp_showroom_mapping.seed.json;."
) else (
    echo [WARN] tp_showroom_mapping.seed.json not found. Build will continue without it.
)

set "CMD=!CMD! --hidden-import irsdk --hidden-import bs4 %SCRIPT%"

echo.
echo [INFO] Building with command:
echo !CMD!
echo.
call !CMD!

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [OK] Build complete.
echo [OK] Output folder: dist\NishizumiPaints
if exist "dist\NishizumiPaints" (
    echo.
    dir /b "dist\NishizumiPaints"
)

echo.
pause
