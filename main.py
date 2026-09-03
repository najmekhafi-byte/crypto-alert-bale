import json
import os
import requests

BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

STATE_FILE = "state.json"

COIN_ALIASES = {
    "bitcoin": "bitcoin", "btc": "bitcoin", "بیتکوین": "bitcoin", "بیت کوین": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum", "اتریوم": "ethereum",
    "tether": "tether", "usdt": "tether", "تتر": "tether",
    "binancecoin": "binancecoin", "bnb": "binancecoin",
    "ripple": "ripple", "xrp": "ripple",
    "cardano": "cardano", "ada": "cardano",
    "solana": "solana", "sol": "solana",
    "dogecoin": "dogecoin", "doge": "dogecoin", "دوج": "dogecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "litecoin": "litecoin", "ltc": "litecoin",
    "tron": "tron", "trx": "tron",
    "shiba-inu": "shiba-inu", "shib": "shiba-inu", "شیبا": "shiba-inu",
    "toncoin": "the-open-network", "ton": "the-open-network",
    "chainlink": "chainlink", "link": "chainlink",
    "avalanche-2": "avalanche-2", "avax": "avalanche-2",
    "polygon": "matic-network", "matic": "matic-network",
}

MENU_KEYBOARD = {
    "keyboard": [
        [{"text": "➕ افزودن آلارم"}],
        [{"text": "📋 لیست آلارم‌ها"}],
        [{"text": "🗑 حذف آلارم"}],
    ],
    "resize_keyboard": True,
}


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_update_id": 0, "alerts": {}, "mode": None}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("alerts", {})
    data.setdefault("mode", None)
    data.setdefault("last_update_id", 0)
    return data


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_prices(coin_ids):
    if not coin_ids:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(sorted(set(coin_ids))), "vs_currencies": "usd"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def send_bale_message(text, with_menu=True):
    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        return
    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": BALE_CHAT_ID, "text": text}
    if with_menu:
        payload["reply_markup"] = MENU_KEYBOARD
    try:
        r = requests.post(url, json=payload, timeout=15)
        print("Bale send:", r.status_code, r.text)
    except Exception as e:
        print("Error sending Bale message:", e)


def send_ntfy_message(text):
    if not NTFY_TOPIC:
        return
    try:
        r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=text.encode("utf-8"), timeout=15)
        print("ntfy send:", r.status_code)
    except Exception as e:
        print("Error sending ntfy message:", e)


def get_bale_updates(offset):
    if not BALE_BOT_TOKEN:
        return []
    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/getUpdates"
    params = {"offset": offset + 1} if offset else {}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception as e:
        print("Error getting Bale updates:", e)
        return []


def format_price(p):
    return str(int(p)) if p == int(p) else str(p)


def parse_alert_command(text):
    parts = text.strip().split()
    if len(parts) != 2:
        return None
    coin_id = COIN_ALIASES.get(parts[0].strip().lower())
    if not coin_id:
        return None
    try:
        price = float(parts[1].replace(",", ""))
    except ValueError:
        return None
    return coin_id, price


def list_alerts_text(state):
    alerts = state.get("alerts", {})
    if not alerts:
        return "هیچ آلارم فعالی ندارید."
    lines = ["📋 آلارم‌های فعال:"]
    for aid, a in alerts.items():
        status = "✅ ارسال شده" if a["triggered"] else "⏳ در انتظار"
        arrow = "بالای" if a["direction"] == "above" else "زیر"
        lines.append(f"{a['coin']} {arrow} {a['price']} — {status}")
    return "\n".join(lines)


def add_alert(state, coin_id, target_price):
    prices = get_prices([coin_id])
    if coin_id not in prices:
        return f"قیمت {coin_id} پیدا نشد."
    current_price = prices[coin_id]["usd"]
    direction = "above" if target_price >= current_price else "below"
    alert_id = f"{coin_id}_{direction}_{format_price(target_price)}"
    state["alerts"][alert_id] = {
        "coin": coin_id, "direction": direction,
        "price": target_price, "triggered": False,
    }
    arrow = "بالاتر رفت از" if direction == "above" else "پایین‌تر آمد از"
    return f"✅ آلارم ثبت شد\n{coin_id}: وقتی قیمت {arrow} {format_price(target_price)} دلار\n(قیمت فعلی: {current_price})"


def process_commands(state):
    updates = get_bale_updates(state.get("last_update_id", 0))
    for update in updates:
        state["last_update_id"] = update["update_id"]
        message = update.get("message")
        if not message or "text" not in message:
            continue
        text = message["text"].strip()

        # دستور شروع -> نمایش منو
        if text.lower() in ("شروع", "start", "/start", "منو"):
            state["mode"] = None
            send_bale_message("سلام 👋 از دکمه‌های پایین استفاده کنید:")
            continue

        # دکمه‌ی افزودن آلارم
        if text == "➕ افزودن آلارم":
            state["mode"] = "awaiting_add"
            send_bale_message("اسم ارز و قیمت رو بفرستید.\nمثال: bitcoin 70000")
            continue

        # دکمه‌ی لیست
        if text == "📋 لیست آلارم‌ها":
            state["mode"] = None
            send_bale_message(list_alerts_text(state))
            continue

        # دکمه‌ی حذف
        if text == "🗑 حذف آلارم":
            alerts = state.get("alerts", {})
            if not alerts:
                state["mode"] = None
                send_bale_message("هیچ آلارمی برای حذف وجود نداره.")
            else:
                state["mode"] = "awaiting_delete"
                send_bale_message(list_alerts_text(state) + "\n\nاسم ارزی که می‌خواید حذف بشه رو بفرستید:")
            continue

        # اگه منتظر دریافت اطلاعات حذف بودیم
        if state.get("mode") == "awaiting_delete":
            target = text.strip().lower()
            removed = [k for k in state.get("alerts", {}) if k.startswith(target)]
            for k in removed:
                del state["alerts"][k]
            state["mode"] = None
            send_bale_message("✅ حذف شد." if removed else "پیدا نشد، دوباره امتحان کنید.")
            continue

        # اگه منتظر دریافت اطلاعات افزودن بودیم (یا مستقیم فرمت درست فرستاده)
        parsed = parse_alert_command(text)
        if parsed is None:
            send_bale_message("متوجه نشدم 🙁\nاز دکمه‌ها استفاده کنید یا فرمت: اسم‌ارز قیمت\nمثال: bitcoin 70000")
            continue

        coin_id, target_price = parsed
        state["mode"] = None
        send_bale_message(add_alert(state, coin_id, target_price))


def check_alerts(state):
    alerts = state.get("alerts", {})
    if not alerts:
        return
    coin_ids = list({a["coin"] for a in alerts.values()})
    prices = get_prices(coin_ids)

    for alert in alerts.values():
        if alert["triggered"]:
            continue
        coin_id = alert["coin"]
        if coin_id not in prices:
            continue
        current_price = prices[coin_id]["usd"]
        direction, target_price = alert["direction"], alert["price"]
        triggered = (
            (direction == "above" and current_price >= target_price) or
            (direction == "below" and current_price <= target_price)
        )
        if triggered:
            arrow = "بالاتر رفت از" if direction == "above" else "پایین‌تر آمد از"
            message = f"🔔 آلارم قیمت\nارز: {coin_id}\nقیمت فعلی: {current_price}\nقیمت {arrow} {target_price}"
            send_bale_message(message)
            send_ntfy_message(message)
            alert["triggered"] = True


def main():
    state = load_state()
    process_commands(state)
    check_alerts(state)
    save_state(state)


if __name__ == "__main__":
    main()
