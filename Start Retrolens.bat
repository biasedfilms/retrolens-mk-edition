@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Retrolens - Mikael Kalesaran Edition

set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PYTHON_INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

echo.
echo  RETROLENS / MIKAEL KALESARAN EDITION
echo  -------------------------------------

if exist "%PYTHON_EXE%" goto :python_ready
set "PYTHON_EXE="
for /f "delims=" %%P in ('py -3.11 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
if defined PYTHON_EXE goto :python_ready

echo Python 3.11 is missing. Downloading the official Python installer for Windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'; exit 0 } catch { exit 1 }"
if errorlevel 1 goto :download_failed
echo Opening the installer. Follow the normal setup window; this launcher will continue afterwards.
start /wait "" "%PYTHON_INSTALLER%" /passive InstallAllUsers=0 Include_launcher=1 PrependPath=0 Include_test=0
del "%PYTHON_INSTALLER%" >nul 2>&1
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" goto :python_missing

:python_ready
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>&1
    if errorlevel 1 rmdir /s /q "%~dp0.venv"
)

if not exist "%VENV_PY%" (
    echo Preparing the app environment for first use...
    "%PYTHON_EXE%" -m venv "%~dp0.venv"
    if errorlevel 1 goto :setup_failed
)

"%VENV_PY%" -c "import cv2, mediapipe, numpy" >nul 2>&1
if errorlevel 1 (
    echo Installing camera and vision components. This may take a few minutes on the first launch...
    "%VENV_PY%" -m pip install --disable-pip-version-check --upgrade pip
    if errorlevel 1 goto :setup_failed
    "%VENV_PY%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
    if errorlevel 1 goto :setup_failed
)

echo Starting the camera. Allow access if Windows asks.
"%VENV_PY%" "%~dp0Retrolens.py"
set "APP_STATUS=%ERRORLEVEL%"
if not "%APP_STATUS%"=="0" (
    echo.
    echo Retrolens stopped with an error. Check the camera permission and the message above.
    pause
)
exit /b %APP_STATUS%

:download_failed
echo Could not download the official Python installer. Check your internet connection.
pause
exit /b 1

:python_missing
echo Python 3.11 was not detected. Finish the Python installer, then run this launcher again.
start "" "https://www.python.org/downloads/release/python-3119/"
pause
exit /b 1

:setup_failed
echo Setup failed. Check your internet connection and try starting Retrolens again.
pause
exit /b 1
