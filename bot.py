import argparse
import asyncio
import json
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from dateutil.parser import parse as parse_time
from playwright.async_api import async_playwright

# ====== KONFIGURACJA ======

DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "7"))
SLOT_MINUTES = int(os.getenv("SLOT_MINUTES", "30"))
MIN_FREE_MINUTES = int(os.getenv("MIN_FREE_MINUTES", "60"))

PRIME_TIME = {
    "weekday": {
        "start": os.getenv("PRIME_WEEKDAY_START", "17:00"),
        "end": os.getenv("PRIME_WEEKDAY_END", "21:00"),
    },
    "weekend": {
        "start": os.getenv("PRIME_WEEKEND_START", "14:00"),
        "end": os.getenv("PRIME_WEEKEND_END", "21:00"),
    },
}

# =========================

BASE_URL = os.getenv("BASE_URL", "https://kluby.org/padel-point-lublin/grafik")
DISCIPLINE = int(os.getenv("DISCIPLINE", "4"))
STATE_FILE = os.getenv("STATE_FILE", "last_seen.json")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("kluby_bot")


def is_weekend(date):
    return date.weekday() >= 5


def get_prime_range(date):
    cfg = PRIME_TIME["weekend" if is_weekend(date) else "weekday"]
    return parse_time(cfg["start"]).time(), parse_time(cfg["end"]).time()


def minutes_from_time(t):
    return t.hour * 60 + t.minute


def format_minutes(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_state(slots):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(list(slots)), f)


def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID env vars.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
        "parse_mode": "Markdown",
    }, timeout=15)
    response.raise_for_status()
    logger.info("Telegram message sent.")


async def scrape_day(page, date):
    url = (
        f"{BASE_URL}"
        f"?data_grafiku={date.strftime('%Y-%m-%d')}"
        f"&dyscyplina={DISCIPLINE}&strona=0"
    )

    await page.goto(url, wait_until="networkidle")
    await page.wait_for_selector("table")

    rows = await page.query_selector_all("table tr")
    prime_start, prime_end = get_prime_range(date)
    prime_start_min = minutes_from_time(prime_start)
    prime_end_min = minutes_from_time(prime_end)

    # {kort: [godziny]}
    free_slots = defaultdict(list)

    for row in rows:
        cells = await row.query_selector_all("td")
        if not cells:
            continue

        hour_text = (await cells[0].inner_text()).strip()
        try:
            hour = parse_time(hour_text).time()
        except Exception:
            continue

        hour_min = minutes_from_time(hour)
        if not (prime_start_min <= hour_min < prime_end_min):
            continue

        for court_idx, cell in enumerate(cells[1:], start=1):
            text = (await cell.inner_text()).strip()
            if "Rezerwuj" in text:
                free_slots[court_idx].append(hour_min)

    return free_slots


def find_continuous_slots(date, free_slots):
    required_slots = math.ceil(MIN_FREE_MINUTES / SLOT_MINUTES)
    found = []

    for court, hours in free_slots.items():
        if not hours:
            continue
        hours = sorted(hours)
        streak_start = hours[0]
        streak_len = 1
        found_for_court = False

        for h in hours[1:]:
            if h - (streak_start + (streak_len - 1) * SLOT_MINUTES) == SLOT_MINUTES:
                streak_len += 1
            else:
                streak_start = h
                streak_len = 1

            if streak_len >= required_slots:
                slot_id = (
                    f"{date.strftime('%Y-%m-%d')} | "
                    f"{format_minutes(streak_start)}–"
                    f"{format_minutes(streak_start + MIN_FREE_MINUTES)} | "
                    f"kort {court}"
                )
                found.append(slot_id)
                found_for_court = True
                break

        if not found_for_court and streak_len >= required_slots:
            slot_id = (
                f"{date.strftime('%Y-%m-%d')} | "
                f"{format_minutes(streak_start)}–"
                f"{format_minutes(streak_start + MIN_FREE_MINUTES)} | "
                f"kort {court}"
            )
            found.append(slot_id)

    return found


def parse_args():
    parser = argparse.ArgumentParser(description="Kluby prime-time watcher")
    parser.add_argument("--dry-run", action="store_true", help="Do not send Telegram message.")
    parser.add_argument("--headful", action="store_true", help="Run browser with UI.")
    parser.add_argument("--days-ahead", type=int, default=DAYS_AHEAD, help="How many days ahead to scan.")
    return parser.parse_args()


async def main():
    args = parse_args()
    previous = load_state()
    current = set()
    new_slots = []

    p = None
    browser = None
    page = None

    async def ensure_browser():
        nonlocal p, browser, page
        if browser is not None:
            return
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=not args.headful,
            args=["--disable-crashpad"],
        )
        page = await browser.new_page(viewport={"width": 1024, "height": 768})

        async def block_heavy_resources(route):
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", block_heavy_resources)

    await ensure_browser()

    for i in range(args.days_ahead):
        date = datetime.now() + timedelta(days=i)
        try:
            free_slots = await scrape_day(page, date)
            continuous = find_continuous_slots(date, free_slots)
        except Exception as exc:
            logger.warning("Failed to scrape %s: %s", date.strftime("%Y-%m-%d"), exc)
            continue

        for slot in continuous:
            current.add(slot)
            if slot not in previous:
                new_slots.append(slot)

    if browser is not None:
        await browser.close()
    if p is not None:
        await p.stop()

    save_state(current)

    if new_slots:
        msg = "🎾 **WOLNE KORTY – PRIME TIME** 🎾\n\n"
        msg += "\n".join(f"• {s}" for s in sorted(new_slots))
        if args.dry_run:
            logger.info("Dry-run message:\n%s", msg)
        else:
            send_telegram(msg)
    elif args.dry_run:
        logger.info("Brak nowych slotow.")


if __name__ == "__main__":
    asyncio.run(main())
