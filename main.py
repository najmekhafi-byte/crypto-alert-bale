import json
import os
import requests

BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

STATE_FILE = "state.json"

# حداکثر تعداد ارزهایی که از CoinGecko بررسی می‌شوند
TOP_COINS_LIMIT = 100

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
        return {
            "last_update_id": 0,
            "alerts": {},
            "mode": None,
            "delete_order": []
        }

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    data.setdefault("alerts", {})
    data.setdefault("mode", None)
    data.setdefault("last_update_id", 0)
    data.setdefault("delete_order", [])

    return data


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_top_coins():
    """
    دریافت 100 ارز اول CoinGecko بر اساس Market Cap
    و ساخت نگاشت:

    BTCUSDT -> bitcoin
    ETHUSDT -> ethereum
    SOLUSDT -> solana
    ...
    """

    url = "https://api.coingecko.com/api/v3/coins/markets"

    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": TOP_COINS_LIMIT,
        "page": 1,
        "sparkline": "false"
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()

        coins = r.json()

        symbol_map = {}

        for coin in coins:
            coin_id = coin.get("id")
            symbol = coin.get("symbol", "").strip().upper()

            if not coin_id or not symbol:
                continue

            pair = f"{symbol}USDT"

            # اگر نماد تکراری بود، اولین مورد را نگه می‌داریم
            if pair not in symbol_map:
                symbol_map[pair] = coin_id

        return symbol_map

    except Exception as e:
        print("Error getting top coins:", e)
        return {}


def get_prices(coin_ids):
    if not coin_ids:
        return {}

    url = "https://api.coingecko.com/api/v3/simple/price"

    params = {
        "ids": ",".join(sorted(set(coin_ids))),
        "vs_currencies": "usd"
    }

    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()

    return r.json()


def send_bale_message(text, with_menu=True):
    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        return

    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": BALE_CHAT_ID,
        "text": text
    }

    if with_menu:
        payload["reply_markup"] = MENU_KEYBOARD

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=15
        )

        print("Bale send:", r.status_code, r.text)

    except Exception as e:
        print("Error sending Bale message:", e)


def send_ntfy_message(text):
    if not NTFY_TOPIC:
        return

    try:
        r = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=text.encode("utf-8"),
            timeout=15
        )

        print("ntfy send:", r.status_code)

    except Exception as e:
        print("Error sending ntfy message:", e)


def get_bale_updates(offset):
    if not BALE_BOT_TOKEN:
        return []

    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/getUpdates"

    params = {"offset": offset + 1} if offset else {}

    try:
        r = requests.get(
            url,
            params=params,
            timeout=15
        )

        r.raise_for_status()

        return r.json().get("result", [])

    except Exception as e:
        print("Error getting Bale updates:", e)
        return []


def format_price(p):
    return str(int(p)) if p == int(p) else str(p)


def parse_alert_command(text):
    """
    فرمت:
    BTCUSDT 100000
    ETHUSDT 4000
    SOLUSDT 200
    """

    parts = text.strip().split()

    if len(parts) != 2:
        return None

    symbol = parts[0].strip().upper()

    # فعلاً فقط جفت‌های USDT معمولی
    if not symbol.endswith("USDT"):
        return None

    # پرپچوال‌ها فعلاً پشتیبانی نمی‌شوند
    if ".P" in symbol:
        return None

    try:
        price = float(parts[1].replace(",", ""))
    except ValueError:
        return None

    # دریافت نگاشت 100 ارز اول
    symbol_map = get_top_coins()

    coin_id = symbol_map.get(symbol)

    if not coin_id:
        return None

    return symbol, coin_id, price


def numbered_alerts_list(state):
    alerts = state.get("alerts", {})

    if not alerts:
        return "هیچ آلارم فعالی ندارید.", []

    ordered_ids = list(alerts.keys())

    lines = ["📋 آلارم‌های فعال:"]

    for i, aid in enumerate(ordered_ids, start=1):
        a = alerts[aid]

        status = "✅ ارسال شده" if a["triggered"] else "⏳ در انتظار"

        arrow = "بالای" if a["direction"] == "above" else "زیر"

        # برای آلارم‌های جدید symbol داریم
        # برای آلارم‌های قدیمی از coin استفاده می‌کنیم
        symbol = a.get("symbol", a.get("coin", ""))

        lines.append(
            f"{i}. {symbol} {arrow} {format_price(a['price'])} — {status}"
        )

    return "\n".join(lines), ordered_ids


def add_alert(state, symbol, coin_id, target_price):
    prices = get_prices([coin_id])

    if coin_id not in prices:
        return f"قیمت {symbol} پیدا نشد."

    current_price = prices[coin_id]["usd"]

    direction = (
        "above"
        if target_price >= current_price
        else "below"
    )

    alert_id = (
        f"{symbol}_{direction}_{format_price(target_price)}"
    )

    state["alerts"][alert_id] = {
        "symbol": symbol,
        "coin": coin_id,
        "direction": direction,
        "price": target_price,
        "triggered": False,
    }

    arrow = (
        "بالاتر رفت از"
        if direction == "above"
        else "پایین‌تر آمد از"
    )

    return (
        f"✅ آلارم ثبت شد\n"
        f"{symbol}: وقتی قیمت {arrow} "
        f"{format_price(target_price)} دلار\n"
        f"(قیمت فعلی: {current_price})"
    )


def process_commands(state):
    updates = get_bale_updates(
        state.get("last_update_id", 0)
    )

    for update in updates:
        state["last_update_id"] = update["update_id"]

        message = update.get("message")

        if not message or "text" not in message:
            continue

        text = message["text"].strip()

        if text.lower() in (
            "شروع",
            "start",
            "/start",
            "منو"
        ):
            state["mode"] = None

            send_bale_message(
                "سلام 👋 از دکمه‌های پایین استفاده کنید:"
            )

            continue

        if text == "➕ افزودن آلارم":
            state["mode"] = "awaiting_add"

            send_bale_message(
                "نماد ارز و قیمت رو بفرستید.\n"
                "مثال:\n"
                "BTCUSDT 100000"
            )

            continue

        if text == "📋 لیست آلارم‌ها":
            state["mode"] = None

            list_text, _ = numbered_alerts_list(state)

            send_bale_message(list_text)

            continue

        if text == "🗑 حذف آلارم":
            list_text, ordered_ids = numbered_alerts_list(state)

            if not ordered_ids:
                state["mode"] = None

                send_bale_message(
                    "هیچ آلارمی برای حذف وجود نداره."
                )

            else:
                state["mode"] = "awaiting_delete"

                state["delete_order"] = ordered_ids

                send_bale_message(
                    list_text +
                    "\n\nشماره‌ی آلارمی که می‌خواید حذف بشه رو بفرستید:"
                )

            continue

        if state.get("mode") == "awaiting_delete":
            ordered_ids = state.get("delete_order", [])

            choice = text.strip()

            if (
                choice.isdigit()
                and 1 <= int(choice) <= len(ordered_ids)
            ):
                target_id = ordered_ids[int(choice) - 1]

                if target_id in state.get("alerts", {}):
                    del state["alerts"][target_id]

                    send_bale_message(
                        "✅ آلارم حذف شد."
                    )

                else:
                    send_bale_message(
                        "این آلارم قبلاً حذف شده بود."
                    )

                state["mode"] = None
                state["delete_order"] = []

            else:
                send_bale_message(
                    "لطفاً فقط شماره‌ی آلارم رو بفرستید (مثلاً: 1)"
                )

            continue

        parsed = parse_alert_command(text)

        if parsed is None:
            send_bale_message(
                "متوجه نشدم 🙁\n"
                "فرمت صحیح:\n"
                "BTCUSDT 100000\n\n"
                "مثال‌های دیگر:\n"
                "ETHUSDT 4000\n"
                "SOLUSDT 200"
            )

            continue

        symbol, coin_id, target_price = parsed

        state["mode"] = None

        result = add_alert(
            state,
            symbol,
            coin_id,
            target_price
        )

        send_bale_message(result)


def check_alerts(state):
    alerts = state.get("alerts", {})

    if not alerts:
        return

    coin_ids = list({
        a["coin"]
        for a in alerts.values()
    })

    try:
        prices = get_prices(coin_ids)
    except Exception as e:
        print("Error checking prices:", e)
        return

    for alert in alerts.values():

        if alert["triggered"]:
            continue

        coin_id = alert["coin"]

        if coin_id not in prices:
            continue

        current_price = prices[coin_id]["usd"]

        direction = alert["direction"]
        target_price = alert["price"]

        triggered = (
            (
                direction == "above"
                and current_price >= target_price
            )
            or
            (
                direction == "below"
                and current_price <= target_price
            )
        )

        if triggered:

            arrow = (
                "بالاتر رفت از"
                if direction == "above"
                else "پایین‌تر آمد از"
            )

            symbol = alert.get(
                "symbol",
                alert.get("coin", "")
            )

            message = (
                f"🔔 آلارم قیمت\n"
                f"ارز: {symbol}\n"
                f"قیمت فعلی: {current_price}\n"
                f"قیمت {arrow} {target_price}"
            )

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
```
