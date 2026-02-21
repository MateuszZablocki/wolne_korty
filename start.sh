#!/usr/bin/env bash
set -euo pipefail

export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/app/.cache/ms-playwright}"

# Ensure browsers exist at runtime if cache was not persisted
playwright install --with-deps chromium

python bot.py
