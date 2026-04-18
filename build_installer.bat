@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo =========================================
echo Nishizumi Paints - Installer Build
echo =========================================
echo.

set "APP_DIR=dist\NishizumiPaints"
set "APP_EXE=%APP_DIR%\NishizumiPaints.exe"
set "ISS=installer\NishizumiPaints.iss"

if not exist "%APP_EXE%" (
    echo [ERROR] App build was not found:
    echo        %APP_EXE%
    echo.
    echo Run build_nobrowser_dir.bat first, then run this installer build again.
    echo.
    pause
    exit /b 1
)

if not exist "%ISS%" (
    echo [ERROR] Inno Setup script was not found:
    echo        %ISS%
    echo.
    pause
    exit /b 1
)

set "APP_VERSION="
for /f "tokens=3 delims= " %%V in ('findstr /B /C:"APP_VERSION" "Nishizumi_Paintsv6_nobrowser.py"') do set "APP_VERSION=%%~V"

if not defined APP_VERSION (
    echo [ERROR] Could not read APP_VERSION from Nishizumi_Paintsv6_nobrowser.py.
    echo.
    pause
    exit /b 1
)

set "ISCC="
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC for %%I in (ISCC.exe) do if not "%%~$PATH:I"=="" set "ISCC=%%~$PATH:I"

if not defined ISCC (
    echo [ERROR] Inno Setup 6 compiler was not found.
    echo.
    echo Install Inno Setup 6, then run this file again:
    echo https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 1
)

echo [INFO] App version: %APP_VERSION%
echo [INFO] Inno compiler: %ISCC%
echo.

"%ISCC%" /DAppVersion=%APP_VERSION% "%ISS%"
if errorlevel 1 (
    echo.
    echo [ERROR] Installer build failed.
    pause
    exit /b 1
)

echo.
echo [OK] Installer build complete.
echo [OK] Output folder: installer\output
if exist "installer\output" (
    echo.
    dir /b "installer\output"
)

echo.
pause
