#!/bin/bash
# Retrolens one-click launcher for macOS.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON_URL="https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg"

say() { printf '\n[Retrolens] %s\n' "$*"; }
pause_for_user() { printf '\nPress Return to close this window... '; read -r _ || true; }

find_python311() {
  local candidate version
  for candidate in \
    "$(command -v python3.11 2>/dev/null || true)" \
    "/opt/homebrew/bin/python3.11" \
    "/opt/homebrew/opt/python@3.11/bin/python3.11" \
    "/usr/local/bin/python3.11" \
    "/usr/local/opt/python@3.11/bin/python3.11" \
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"; do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    version="$($candidate -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    if [ "$version" = "3.11" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

say "RETROLENS / MIKAEL KALESARAN EDITION"
PYTHON_BIN="$(find_python311 || true)"

if [ -z "$PYTHON_BIN" ]; then
  BREW_BIN="$(command -v brew 2>/dev/null || true)"
  if [ -z "$BREW_BIN" ] && [ -x "/opt/homebrew/bin/brew" ]; then BREW_BIN="/opt/homebrew/bin/brew"; fi
  if [ -z "$BREW_BIN" ] && [ -x "/usr/local/bin/brew" ]; then BREW_BIN="/usr/local/bin/brew"; fi
  if [ -n "$BREW_BIN" ]; then
    say "Installing a compatible Python 3.11 through Homebrew..."
    "$BREW_BIN" install python@3.11 || true
    PYTHON_BIN="$(find_python311 || true)"
  fi
fi

if [ -z "$PYTHON_BIN" ]; then
  say "Python 3.11 is missing. Downloading the official Python installer (one-time setup)..."
  PKG_PATH="${TMPDIR:-/tmp}/python-3.11.9-macos11.pkg"
  if ! curl --fail --location --silent --show-error --retry 2 "$PYTHON_URL" -o "$PKG_PATH"; then
    say "The Python installer could not be downloaded. Check your internet connection and try again."
    open "https://www.python.org/downloads/release/python-3119/" >/dev/null 2>&1 || true
    pause_for_user
    exit 1
  fi
  say "Opening the official installer. Complete its normal macOS installation window; this launcher will continue automatically."
  open "$PKG_PATH"
  for ((attempt=0; attempt<300; attempt++)); do
    PYTHON_BIN="$(find_python311 || true)"
    [ -n "$PYTHON_BIN" ] && break
    sleep 2
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  say "Python 3.11 was not detected. Finish the Python installer, then double-click this launcher again."
  open "https://www.python.org/downloads/release/python-3119/" >/dev/null 2>&1 || true
  pause_for_user
  exit 1
fi

VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"
if [ -x "$VENV_PY" ]; then
  VENV_VERSION="$($VENV_PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [ "$VENV_VERSION" != "3.11" ]; then
    say "Refreshing the local environment to use Python 3.11..."
    rm -rf "$VENV"
  fi
fi

if [ ! -x "$VENV_PY" ]; then
  say "Preparing the app environment (one-time setup)..."
  if ! "$PYTHON_BIN" -m venv "$VENV"; then
    say "Could not create the app environment. Make sure this folder is writable."
    pause_for_user
    exit 1
  fi
fi

if ! "$VENV_PY" -c 'import cv2, mediapipe, numpy' >/dev/null 2>&1; then
  say "Installing camera and vision components. This may take a few minutes on the first launch..."
  if ! "$VENV_PY" -m pip install --disable-pip-version-check --upgrade pip; then
    say "Dependency setup failed while preparing pip. Check your internet connection."
    pause_for_user
    exit 1
  fi
  if ! "$VENV_PY" -m pip install --disable-pip-version-check -r "$ROOT/requirements.txt"; then
    say "Dependency setup failed. Check your internet connection and run this launcher again."
    pause_for_user
    exit 1
  fi
fi

say "Starting the camera. Allow camera access if macOS asks."
"$VENV_PY" "$ROOT/Retrolens.py"
APP_STATUS=$?
if [ "$APP_STATUS" -ne 0 ]; then
  say "Retrolens stopped with an error. Check the message above and the camera permission in System Settings."
  pause_for_user
fi
exit "$APP_STATUS"
