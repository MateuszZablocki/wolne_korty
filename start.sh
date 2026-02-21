#!/usr/bin/env bash
set -euo pipefail

export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/app/.cache/ms-playwright}"

if [[ ! -x "$PLAYWRIGHT_BROWSERS_PATH/chromium_headless_shell" ]]; then
  # Ensure browsers exist at runtime if cache was not persisted
  playwright install --with-deps chromium
fi

python bot.py
