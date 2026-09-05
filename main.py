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
        [{"text": "⭐ ارزهای مورد علاقه"}, {"text": "➕ افزودن آلارم"}],
        [{"text": "📋 لیست آلارم‌ها"}],
        [{"text": "🗑 حذف آلارم"}, {"text": "🗑 حذف همه آلارم‌ها"}],
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

BACK_KEYBOARD = {
    "keyboard": [[{"text": "🔙 بازگشت"}]],
    "resize_keyboard": True,
}

KRAKEN_PAIRS = {
    "BTCUSDT": "XBTUSD",
    "ETHUSDT": "ETHUSD",
    "XRPUSDT": "XRPUSD",
    "ADAUSDT": "ADAUSD",
    "SOLUSDT": "SOLUSD",
    "DOGEUSDT": "DOGEUSD",
    "DOTUSDT": "DOTUSD",
    "LTCUSDT": "LTCUSD",
    "TRXUSDT": "TRXUSD",
    "SHIBUSDT": "SHIBUSD",
    "LINKUSDT": "LINKUSD",
    "AVAXUSDT": "AVAXUSD",
}

MANUAL_COINGECKO_IDS = {
    "XAUUSDT": "tether-gold",
    "XAUTUSDT": "tether-gold",
}

_TOP100_ID_MAP = None


def get_top100_id_map():
    global _TOP100_ID_MAP
    if _TOP100_ID_MAP is not None:
        return _TOP100_ID_MAP
    id_map = {}
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 100, "page": 1},
            timeout=20,
        )
        r.raise_for_status()
        for coin in r.json():
            symbol = coin.get("symbol", "").upper() + "USDT"
            coin_id = coin.get("id")
            if symbol and coin_id and symbol not in id_map:
                id_map[symbol] = coin_id
        print(f"Top100 list loaded: {len(id_map)} coins")
    except Exception as e:
        print("Error fetching top100 list:", e)
    _TOP100_ID_MAP = id_map
    return _TOP100_ID_MAP


def resolve_coingecko_id(symbol):
    if symbol in MANUAL_COINGECKO_IDS:
        return MANUAL_COINGECKO_IDS[symbol]
    return get_top100_id_map().get(symbol)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "last_update_id": 0, "alerts": {}, "mode": None,
            "delete_order": [], "favorites": [], "selected_symbol": None,
            "fav_delete_order": [],
        }
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("alerts", {})
    data.setdefault("mode", None)
    data.setdefault("last_update_id", 0)
    data.setdefault("delete_order", [])
    data.setdefault("favorites", [])
    data.setdefault("selected_symbol", None)
    data.setdefault("fav_delete_order", [])
    return data


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_kraken_prices(symbols):
    prices = {}
    for symbol in symbols:
        kraken_pair = KRAKEN_PAIRS.get(symbol)
        if not kraken_pair:
            continue
        try:
            r = requests.get(
                "https://api.kraken.com/0/public/Ticker",
                params={"pair": kraken_pair},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get("error"):
                continue
            result = data.get("result", {})
            if not result:
                continue
            first_key = next(iter(result))
            prices[symbol] = float(result[first_key]["c"][0])
        except Exception as e:
            print(f"Kraken request error for {symbol}: {e}")
    return prices


def get_coingecko_prices(symbols):
    if not symbols:
        return {}
    coin_id_to_symbols = {}
    for symbol in symbols:
        coin_id = resolve_coingecko_id(symbol)
        if coin_id:
            coin_id_to_symbols.setdefault(coin_id, []).append(symbol)
    if not coin_id_to_symbols:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(sorted(coin_id_to_symbols.keys())), "vs_currencies": "usd"}
    prices = {}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for coin_id, syms in coin_id_to_symbols.items():
            if coin_id in data and "usd" in data[coin_id]:
                price = float(data[coin_id]["usd"])
                for symbol in syms:
                    prices[symbol] = price
    except Exception as e:
        print(f"CoinGecko error: {e}")
    return prices


def get_prices(symbols):
    if not symbols:
        return {}
    symbols = list({s.upper() for s in symbols if s})
    kraken_candidates = [s for s in symbols if s in KRAKEN_PAIRS]
    prices = get_kraken_prices(kraken_candidates)
    missing = [s for s in symbols if s not in prices]
    if missing:
        prices.update(get_coingecko_prices(missing))
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


def pct_distance(current, target):
    if not current:
        return "نامشخص"
    pct = abs(target - current) / current * 100
    return f"{pct:.1f}%"


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
    symbols = list({a.get("symbol", a.get("coin")) for a in alerts.values()})
    prices = get_prices(symbols)
    lines = ["📋 آلارم‌های فعال:"]
    for i, aid in enumerate(ordered_ids, start=1):
        a = alerts[aid]
        symbol = a.get("symbol", a.get("coin", ""))
        status = "✅ ارسال شده" if a["triggered"] else "⏳ در انتظار"
        arrow = "بالای" if a["direction"] == "above" else "زیر"
        current = prices.get(symbol)
        if current and not a["triggered"]:
            dist = pct_distance(current, a["price"])
            lines.append(f"{i}. {symbol} {arrow} {a['price']} — {status} (فاصله: {dist})")
        else:
            lines.append(f"{i}. {symbol} {arrow} {a['price']} — {status}")
    return "\n".join(lines), ordered_ids


def create_alert_reply(state, symbol, target_price, current_price):
    direction = "above" if target_price >= current_price else "below"
    alert_id = f"{symbol}_{direction}_{format_price(target_price)}"
    state["alerts"][alert_id] = {
        "symbol": symbol, "direction": direction,
        "price": target_price, "triggered": False,
    }
    arrow = "بالاتر رفت از" if direction == "above" else "پایین‌تر آمد از"
    dist = pct_distance(current_price, target_price)
    return (
        f"✅ آلارم ثبت شد\n{symbol}: وقتی قیمت {arrow} {format_price(target_price)} دلار\n"
        f"(قیمت فعلی: {format_price(current_price)} — فاصله: {dist})"
    )


def process_add_lines(state, text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    parsed_list, invalid_lines = [], []
    for line in lines:
        parsed = parse_alert_command(line)
        if parsed is None:
            invalid_lines.append(line)
        else:
            parsed_list.append(parsed)

    symbols_needed = list({symbol for symbol, _ in parsed_list})
    prices = get_prices(symbols_needed)

    replies, any_valid = [], False
    for symbol, target_price in parsed_list:
        if symbol not in prices:
            replies.append(f"❌ قیمت {symbol} پیدا نشد (ممکنه نماد پشتیبانی نشه).")
            continue
        any_valid = True
        replies.append(create_alert_reply(state, symbol, target_price, prices[symbol]))

    for line in invalid_lines:
        replies.append(f"❌ نامعتبر: {line}")

    return "\n\n".join(replies), any_valid


def parse_delete_numbers(text, max_n):
    numbers = re.findall(r"\d+", text)
    result, seen = [], set()
    for n in numbers:
        idx = int(n)
        if 1 <= idx <= max_n and idx not in seen:
            seen.add(idx)
            result.append(idx)
    return result


def favorites_keyboard(favorites):
    rows = []
    for i in range(0, len(favorites), 2):
        chunk = favorites[i:i + 2]
        rows.append([{"text": s} for s in chunk])
    rows.append([{"text": "➕ افزودن ارز جدید"}, {"text": "🗑 حذف از لیست"}])
    rows.append([{"text": "🔙 بازگشت"}])
    return {"keyboard": rows, "resize_keyboard": True}


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

        if text == "🔙 بازگشت":
            state["mode"] = None
            send_bale_message("منوی اصلی:")
            continue

        # ---------- افزودن آلارم با تایپ نماد ----------
        if text == "➕ افزودن آلارم":
            state["mode"] = "awaiting_add"
            send_bale_message(
                "نماد ارز و قیمت رو بفرستید.\nمثال: BTCUSDT 100000\n\n"
                "برای چند آلارم هم‌زمان، هر کدوم رو در یک خط جدا بنویسید:\n"
                "BTCUSDT 77000\nETHUSDT 4000"
            )
            continue

        # ---------- ارزهای مورد علاقه ----------
        if text == "⭐ ارزهای مورد علاقه":
            favorites = state.get("favorites", [])
            state["mode"] = "fav_menu"
            if not favorites:
                send_bale_message(
                    "لیست علاقه‌مندی‌هاتون خالیه.\nبا دکمه‌ی زیر یه ارز اضافه کنید:",
                    with_menu=False, custom_keyboard=favorites_keyboard([]),
                )
            else:
                send_bale_message(
                    "یه ارز رو انتخاب کنید:",
                    with_menu=False, custom_keyboard=favorites_keyboard(favorites),
                )
            continue

        if state.get("mode") == "fav_menu":
            favorites = state.get("favorites", [])

            if text == "➕ افزودن ارز جدید":
                state["mode"] = "awaiting_fav_add"
                send_bale_message(
                    "نماد ارز رو بفرستید (مثلاً BTCUSDT):",
                    with_menu=False, custom_keyboard=BACK_KEYBOARD,
                )
                continue

            if text == "🗑 حذف از لیست":
                if not favorites:
                    send_bale_message("لیست خالیه.", with_menu=False, custom_keyboard=favorites_keyboard(favorites))
                else:
                    lines = ["لیست علاقه‌مندی‌ها:"]
                    for i, s in enumerate(favorites, start=1):
                        lines.append(f"{i}. {s}")
                    state["mode"] = "awaiting_fav_delete"
                    state["fav_delete_order"] = favorites.copy()
                    send_bale_message(
                        "\n".join(lines) + "\n\nشماره‌ی مورد نظر رو بفرستید:",
                        with_menu=False, custom_keyboard=BACK_KEYBOARD,
                    )
                continue

            if text in favorites:
                state["mode"] = "awaiting_fav_price"
                state["selected_symbol"] = text
                send_bale_message(
                    f"قیمت هدف برای {text} رو بفرستید:",
                    with_menu=False, custom_keyboard=BACK_KEYBOARD,
                )
                continue

            send_bale_message(
                "لطفاً از دکمه‌های موجود استفاده کنید.",
                with_menu=False, custom_keyboard=favorites_keyboard(favorites),
            )
            continue

        if state.get("mode") == "awaiting_fav_add":
            symbol = text.strip().upper()
            if not symbol.endswith("USDT"):
                send_bale_message(
                    "فرمت درست نیست. مثال: BTCUSDT",
                    with_menu=False, custom_keyboard=BACK_KEYBOARD,
                )
                continue
            favorites = state.get("favorites", [])
            if symbol not in favorites:
                favorites.append(symbol)
                state["favorites"] = favorites
            state["mode"] = "fav_menu"
            send_bale_message(
                f"✅ {symbol} به علاقه‌مندی‌ها اضافه شد.",
                with_menu=False, custom_keyboard=favorites_keyboard(favorites),
            )
            continue

        if state.get("mode") == "awaiting_fav_delete":
            fav_order = state.get("fav_delete_order", [])
            numbers = parse_delete_numbers(text, len(fav_order))
            favorites = state.get("favorites", [])
            if numbers:
                to_remove = {fav_order[i - 1] for i in numbers}
                favorites = [s for s in favorites if s not in to_remove]
                state["favorites"] = favorites
            state["mode"] = "fav_menu"
            send_bale_message(
                "✅ به‌روزرسانی شد." if numbers else "چیزی حذف نشد.",
                with_menu=False, custom_keyboard=favorites_keyboard(favorites),
            )
            continue

        if state.get("mode") == "awaiting_fav_price":
            symbol = state.get("selected_symbol")
            try:
                target_price = float(text.strip().replace(",", ""))
            except ValueError:
                send_bale_message(
                    "لطفاً فقط عدد قیمت رو بفرستید.",
                    with_menu=False, custom_keyboard=BACK_KEYBOARD,
                )
                continue
            prices = get_prices([symbol])
            state["mode"] = "fav_menu"
            if symbol not in prices:
                send_bale_message(
                    f"❌ قیمت {symbol} پیدا نشد.",
                    with_menu=False, custom_keyboard=favorites_keyboard(state.get("favorites", [])),
                )
                continue
            reply = create_alert_reply(state, symbol, target_price, prices[symbol])
            send_bale_message(reply, with_menu=False, custom_keyboard=favorites_keyboard(state.get("favorites", [])))
            continue

        # ---------- لیست آلارم‌ها ----------
        if text == "📋 لیست آلارم‌ها":
            state["mode"] = None
            list_text, _ = numbered_alerts_list(state)
            send_bale_message(list_text)
            continue

        # ---------- حذف آلارم ----------
        if text == "🗑 حذف آلارم":
            list_text, ordered_ids = numbered_alerts_list(state)
            if not ordered_ids:
                state["mode"] = None
                send_bale_message("هیچ آلارمی برای حذف وجود نداره.")
            else:
                state["mode"] = "awaiting_delete"
                state["delete_order"] = ordered_ids
                send_bale_message(
                    list_text + "\n\nشماره‌ی آلارم(ها) رو بفرستید (مثلاً: 1 3 5):"
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
                    with_menu=False, custom_keyboard=DELETE_ALL_KEYBOARD,
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
                    with_menu=False, custom_keyboard=DELETE_ALL_KEYBOARD,
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

        # ---------- افزودن مستقیم با تایپ ----------
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
