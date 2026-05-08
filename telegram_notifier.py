import os
from datetime import datetime, time, timedelta, timezone

import requests

APP_TIMEZONE_NAME = "Asia/Kolkata"

try:
    from zoneinfo import ZoneInfo

    APP_TZ = ZoneInfo(APP_TIMEZONE_NAME)

except Exception:
    APP_TZ = timezone(timedelta(hours=5, minutes=30))


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

NOTIFIED = {}


def now_tz():
    return datetime.now(APP_TZ)


def market_hours_open():
    now = now_tz()

    if now.weekday() >= 5:
        return False

    start = time(9, 15)
    end = time(15, 15)

    return start <= now.time() <= end


def send_telegram_message(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing")
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=10,
        )

    except Exception as exc:
        print(f"Telegram send error: {exc}")


def should_notify(key, cooldown_seconds=1800):

    now = now_tz()
    last_sent = NOTIFIED.get(key)

    if last_sent is None:
        NOTIFIED[key] = now
        return True

    diff = (now - last_sent).total_seconds()

    if diff >= cooldown_seconds:
        NOTIFIED[key] = now
        return True

    return False


def check_and_notify(rows):

    if not market_hours_open():
        return

    for row in rows:
        app_name = row.get("app_name", "Unknown App")

        # OFFLINE ALERT
        if not row.get("online", False):
            key = f"{app_name}_offline"
            if should_notify(key):
                send_telegram_message(f"🚨 {app_name} is OFFLINE")

        # DAILY LOGIN ALERT
        if not row.get("daily_login", False):
            key = f"{app_name}_daily_login"
            if should_notify(key):
                send_telegram_message(f"⚠️ Daily Login NOT done for {app_name}")

        # DB RESET ALERT
        if not row.get("db_reset", False):
            key = f"{app_name}_db_reset"
            if should_notify(key):
                send_telegram_message(f"⚠️ DB Reset NOT done for {app_name}")
