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


def
