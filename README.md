# kluby_bot

Bot sprawdza wolne sloty w prime time i wysyla powiadomienia na Telegram.

## Wymagania
- Python 3.10+
- Playwright

## Lokalny start
1. `python -m venv .venv`
2. `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `playwright install chromium`
5. Ustaw zmienne srodowiskowe:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
6. Uruchom:
   - `python bot.py --dry-run` (bez wysylania na Telegram)
   - `python bot.py` (wysyla, gdy sa nowe sloty)
7. Skrypt do lokalnego testu (wczyta `.env`, uruchomi przegladarke i nie wysle na Telegram):
   - `scripts/run_local.sh`

## Konfiguracja przez env
- `DAYS_AHEAD` (domyslnie 7)
- `SLOT_MINUTES` (domyslnie 30)
- `MIN_FREE_MINUTES` (domyslnie 60)
- `BASE_URL` (domyslnie https://kluby.org/padel-point-lublin/grafik)
- `DISCIPLINE` (domyslnie 4)
- `STATE_FILE` (domyslnie last_seen.json)
- `PRIME_WEEKDAY_START` / `PRIME_WEEKDAY_END`
- `PRIME_WEEKEND_START` / `PRIME_WEEKEND_END`

## Railway
1. Dodaj repo na Railway.
2. Ustaw zmienne env (jak wyzej).
3. Dodaj komende build lub predeploy:
   - `pip install -r requirements.txt`
   - `playwright install chromium`
4. Start command jest w `Procfile`:
   - `worker: python bot.py`
5. Dodaj scheduler (cron) w Railway:
   - wyzwalaj co 30 minut: `*/30 * * * *`

Uwagi:
- `STATE_FILE` trzyma informacje o ostatnio widzianych slotach. Na Railway moze byc ulotny, chyba ze dodasz wolumen lub inny storage.
- Dla testow lokalnych uzyj `--dry-run`, zeby nie wysylac wiadomosci.
- Logi zapisuja sie do pliku `bot.log` (konfigurowalne przez `LOG_FILE`).
