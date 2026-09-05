import json
import os
import re
import requests

BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT_ID = os.environ.get("BALE_CHAT_ID")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

STATE_FILE = "state.json"

MENU_KEYBOARD = {
    "keyboard": [
        [{"text": "➕ افزودن آلارم"}],
        [{"text": "📋 لیست آلارم‌ها"}],
        [{"text": "🗑 حذف آلارم"}],
        [{"text": "🗑 حذف همه آلارم‌ها"}],
    ],
    "resize_keyboard": True,
}

DELETE_ALL_KEYBOARD = {
    "keyboard": [
        [{"text": "✅ بله، حذف همه"}],
        [{"text": "❌ انصراف"}],
    ],
    "resize_keyboard": True,
}

COINGECKO_IDS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "ADAUSDT": "cardano",
    "SOLUSDT": "solana",
    "DOGEUSDT": "dogecoin",
    "DOTUSDT": "polkadot",
    "LTCUSDT": "litecoin",
    "TRXUSDT": "tron",
    "SHIBUSDT": "shiba-inu",
    "TONUSDT": "the-open-network",
    "LINKUSDT": "chainlink",
    "AVAXUSDT": "avalanche-2",
    "MATICUSDT": "matic-network",
    "XAUTUSDT": "tether-gold",
}


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_update_id": 0, "alerts": {}, "mode": None, "delete_order": []}
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


def get_binance_futures_prices(symbols):
    if not symbols:
        return {}
    prices = {}
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    for symbol in sorted(set(symbols)):
        symbol = symbol.upper()
        try:
            r = requests.get(url, params={"symbol": symbol}, timeout=15)
            print(f"Binance Futures response for {symbol}: {r.status_code} {r.text}")
            if r.status_code != 200:
                print(f"Binance Futures unavailable for {symbol}: HTTP {r.status_code}")
                continue
            data = r.json()
            if "symbol" in data and "price" in data:
                prices[symbol] = float(data["price"])
            else:
                print(f"Unexpected Binance response for {symbol}: {data}")
        except requests.exceptions.RequestException as e:
            print(f"Binance Futures request error for {symbol}: {e}")
        except (ValueError, TypeError, KeyError) as e:
            print(f"Binance Futures data error for {symbol}: {e}")
        except Exception as e:
            print(f"Unexpected Binance error for {symbol}: {e}")
    return prices


def get_coingecko_prices(symbols):
    if not symbols:
        return {}
    coin_ids = []
    for symbol in symbols:
        symbol = symbol.upper()
        if symbol in COINGECKO_IDS:
            coin_ids.append(COINGECKO_IDS[symbol])
        else:
            print(f"No CoinGecko mapping for {symbol}")
    if not coin_ids:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(sorted(set(coin_ids))), "vs_currencies": "usd"}
    try:
        r = requests.get(url, params=params, timeout=15)
        print(f"CoinGecko response: {r.status_code} {r.text}")
        r.raise_for_status()
        data = r.json()
        prices = {}
        for symbol in symbols:
            symbol = symbol.upper()
            coin_id = COINGECKO_IDS.get(symbol)
            if coin_id and coin_id in data and "usd" in data[coin_id]:
                prices[symbol] = float(data[coin_id]["usd"])
        return prices
    except requests.exceptions.RequestException as e:
        print(f"CoinGecko request error: {e}")
    except (ValueError, TypeError, KeyError) as e:
        print(f"CoinGecko data error: {e}")
    except Exception as e:
        print(f"Unexpected CoinGecko error: {e}")
    return {}


def get_prices(symbols):
    if not symbols:
        return {}
    symbols = [symbol.upper() for symbol in symbols if symbol]
    prices = get_binance_futures_prices(symbols)
    missing_symbols = [symbol for symbol in symbols if symbol not in prices]
    if missing_symbols:
        print("Binance Futures unavailable for:", missing_symbols)
        print("Trying CoinGecko fallback...")
        fallback_prices = get_coingecko_prices(missing_symbols)
        for symbol, price in fallback_prices.items():
            prices[symbol] = price
            print(f"CoinGecko fallback price for {symbol}: {price}")
    return prices


def send_bale_message(text, with_menu=True, custom_keyboard=None):
    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        return
    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": BALE_CHAT_ID, "text": text}
    if custom_keyboard is not None:
        payload["reply_markup"] = custom_keyboard
    elif with_menu:
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
    symbol = parts[0].strip().upper()
    if not symbol.endswith("USDT"):
        return None
    try:
        price = float(parts[1].replace(",", ""))
    except ValueError:
        return None
    return symbol, price


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
        symbol = a.get("symbol", a.get("coin", ""))
        lines.append(f"{i}. {symbol} {arrow} {a['price']} — {status}")
    return "\n".join(lines), ordered_ids


def add_alert(state, symbol, target_price):
    prices = get_prices([symbol])
    if symbol not in prices:
        return f"❌ قیمت {symbol} در Binance Futures و CoinGecko پیدا نشد."
    current_price = prices[symbol]
    direction = "above" if target_price >= current_price else "below"
    alert_id = f"{symbol}_{direction}_{format_price(target_price)}"
    state["alerts"][alert_id] = {
        "symbol": symbol,
        "direction": direction,
        "price": target_price,
        "triggered": False,
    }
    arrow = "بالاتر رفت از" if direction == "above" else "پایین‌تر آمد از"
    return (
        f"✅ آلارم ثبت شد\n{symbol}: وقتی قیمت {arrow} "
        f"{format_price(target_price)} دلار\n(قیمت فعلی: {format_price(current_price)})"
    )


def process_add_lines(state, text):
    """هر خط از پیام رو به‌عنوان یه آلارم جدا پردازش می‌کنه."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    replies = []
    any_valid = False
    for line in lines:
        parsed = parse_alert_command(line)
        if parsed is None:
            replies.append(f"❌ نامعتبر: {line}")
        else:
            any_valid = True
            symbol, target_price = parsed
            replies.append(add_alert(state, symbol, target_price))
    return "\n\n".join(replies), any_valid


def parse_delete_numbers(text, max_n):
    """همه‌ی شماره‌های موجود در پیام رو استخراج می‌کنه (با فاصله، ویرگول، یا 'و' جدا شده باشن)."""
    numbers = re.findall(r"\d+", text)
    result = []
    seen = set()
    for n in numbers:
        idx = int(n)
        if 1 <= idx <= max_n and idx not in seen:
            seen.add(idx)
            result.append(idx)
    return result


def process_commands(state):
    updates = get_bale_updates(state.get("last_update_id", 0))
    for update in updates:
        state["last_update_id"] = update["update_id"]
        message = update.get("message")
        if not message or "text" not in message:
            continue
        text = message["text"].strip()

        if text.lower() in ("شروع", "start", "/start", "منو"):
            state["mode"] = None
            send_bale_message("سلام 👋 از دکمه‌های پایین استفاده کنید:")
            continue

        if text == "➕ افزودن آلارم":
            state["mode"] = "awaiting_add"
            send_bale_message(
                "نماد ارز و قیمت رو بفرستید.\nمثال: BTCUSDT 100000\n\n"
                "برای چند آلارم هم‌زمان، هر کدوم رو در یک خط جدا بنویسید:\n"
                "BTCUSDT 77000\nETHUSDT 4000"
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
                send_bale_message("هیچ آلارمی برای حذف وجود نداره.")
            else:
                state["mode"] = "awaiting_delete"
                state["delete_order"] = ordered_ids
                send_bale_message(
                    list_text + "\n\nشماره‌ی آلارم(ها) رو بفرستید.\n"
                    "برای چندتایی، با فاصله بنویسید: 1 3 5"
                )
            continue

        if text == "🗑 حذف همه آلارم‌ها":
            if not state.get("alerts"):
                state["mode"] = None
                send_bale_message("هیچ آلارمی برای حذف وجود نداره.")
            else:
                state["mode"] = "awaiting_delete_all"
                send_bale_message(
                    "⚠️ مطمئن هستید که می‌خواهید همه آلارم‌ها حذف شوند؟",
                    with_menu=False,
                    custom_keyboard=DELETE_ALL_KEYBOARD,
                )
            continue

        if state.get("mode") == "awaiting_delete_all":
            if text == "✅ بله، حذف همه":
                state["alerts"] = {}
                state["delete_order"] = []
                state["mode"] = None
                send_bale_message("✅ همه آلارم‌ها با موفقیت حذف شدند.")
            elif text == "❌ انصراف":
                state["mode"] = None
                state["delete_order"] = []
                send_bale_message("❌ حذف همه آلارم‌ها لغو شد.")
            else:
                send_bale_message(
                    "لطفاً یکی از دکمه‌های بالا را انتخاب کنید.",
                    with_menu=False,
                    custom_keyboard=DELETE_ALL_KEYBOARD,
                )
            continue

        if state.get("mode") == "awaiting_delete":
            ordered_ids = state.get("delete_order", [])
            numbers = parse_delete_numbers(text, len(ordered_ids))
            if numbers:
                deleted_symbols = []
                for idx in numbers:
                    target_id = ordered_ids[idx - 1]
                    if target_id in state.get("alerts", {}):
                        deleted_symbols.append(state["alerts"][target_id].get("symbol", target_id))
                        del state["alerts"][target_id]
                state["mode"] = None
                state["delete_order"] = []
                if deleted_symbols:
                    send_bale_message("✅ آلارم‌های زیر حذف شدند:\n" + "\n".join(deleted_symbols))
                else:
                    send_bale_message("این آلارم(ها) قبلاً حذف شده بودند.")
            else:
                send_bale_message("لطفاً شماره‌ی آلارم(ها) رو بفرستید (مثلاً: 1 3 5)")
            continue

        reply, any_valid = process_add_lines(state, text)
        state["mode"] = None
        if not any_valid:
            send_bale_message(
                "متوجه نشدم 🙁\nفرمت صحیح:\nنماد ارز قیمت\n\nمثال:\nBTCUSDT 100000\n\n"
                "برای چند آلارم هم‌زمان، هر خط یه آلارم:\nBTCUSDT 77000\nETHUSDT 4000"
            )
        else:
            send_bale_message(reply)


def check_alerts(state):
    alerts = state.get("alerts", {})
    if not alerts:
        return
    symbols = list({a.get("symbol", a.get("coin")) for a in alerts.values()})
    prices = get_prices(symbols)
    for alert in alerts.values():
        if alert["triggered"]:
            continue
        symbol = alert.get("symbol", alert.get("coin"))
        if symbol not in prices:
            continue
        current_price = prices[symbol]
        direction = alert["direction"]
        target_price = alert["price"]
        triggered = (
            (direction == "above" and current_price >= target_price)
            or (direction == "below" and current_price <= target_price)
        )
        if triggered:
            arrow = "بالاتر رفت از" if direction == "above" else "پایین‌تر آمد از"
            message = (
                f"🔔 آلارم قیمت\nارز: {symbol}\nقیمت فعلی: {format_price(current_price)}\n"
                f"قیمت {arrow} {format_price(target_price)}"
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
