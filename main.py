import json
import os
import sys
import requests

# ---------- خواندن اطلاعات حساس از GitHub Secrets ----------
BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_prices(coin_ids):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(coin_ids), "vs_currencies": "usd"}
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def send_bale_message(text):
    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        print("Bale token/chat_id not set, skipping Bale message.")
        return
    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": BALE_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=15)
        print("Bale response:", r.status_code, r.text)
    except Exception as e:
        print("Error sending Bale message:", e)


def send_ntfy_message(text):
    if not NTFY_TOPIC:
        print("ntfy topic not set, skipping ntfy message.")
        return
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    try:
        r = requests.post(url, data=text.encode("utf-8"), timeout=15)
        print("ntfy response:", r.status_code)
    except Exception as e:
        print("Error sending ntfy message:", e)


def main():
    config = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)

    coin_ids = list(config.keys())
    prices = get_prices(coin_ids)

    state_changed = False

    for coin_id, alerts in config.items():
        if coin_id not in prices:
            print(f"Warning: no price data for {coin_id}")
            continue

        current_price = prices[coin_id]["usd"]
        print(f"{coin_id}: current price = {current_price}")

        for alert in alerts:
            alert_id = alert["id"]
            direction = alert["direction"]
            target_price = alert["price"]

            already_triggered = state.get(alert_id, {}).get("triggered", False)

            if already_triggered:
                continue

            should_trigger = False
            if direction == "above" and current_price >= target_price:
                should_trigger = True
            elif direction == "below" and current_price <= target_price:
                should_trigger = True

            if should_trigger:
                direction_fa = "بالاتر رفت از" if direction == "above" else "پایین‌تر آمد از"
                message = (
                    f"🔔 آلارم قیمت\n"
                    f"ارز: {coin_id}\n"
                    f"قیمت فعلی: {current_price} دلار\n"
                    f"قیمت {direction_fa} {target_price} دلار"
                )
                print("Triggering alert:", alert_id)
                send_bale_message(message)
                send_ntfy_message(message)

                state[alert_id] = {"triggered": True}
                state_changed = True

    if state_changed:
        save_json(STATE_FILE, state)
        print("State updated.")
    else:
        print("No new alerts triggered.")


if __name__ == "__main__":
    main()
