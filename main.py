import json
import os
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


# --------------------------------------------------
# CoinGecko fallback mapping
# --------------------------------------------------

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


# --------------------------------------------------
# Binance Futures
# --------------------------------------------------

def get_binance_futures_prices(symbols):
    if not symbols:
        return {}

    prices = {}

    url = "https://fapi.binance.com/fapi/v1/ticker/price"

    for symbol in sorted(set(symbols)):
        symbol = symbol.upper()

        try:
            r = requests.get(
                url,
                params={"symbol": symbol},
                timeout=15
            )

            print(
                f"Binance Futures response for {symbol}: "
                f"{r.status_code} {r.text}"
            )

            if r.status_code != 200:
                print(
                    f"Binance Futures unavailable for "
                    f"{symbol}: HTTP {r.status_code}"
                )
                continue

            data = r.json()

            if "symbol" in data and "price" in data:
                prices[symbol] = float(data["price"])
            else:
                print(
                    f"Unexpected Binance response for "
                    f"{symbol}: {data}"
                )

        except requests.exceptions.RequestException as e:
            print(
                f"Binance Futures request error for "
                f"{symbol}: {e}"
            )

        except (ValueError, TypeError, KeyError) as e:
            print(
                f"Binance Futures data error for "
                f"{symbol}: {e}"
            )

        except Exception as e:
            print(
                f"Unexpected Binance error for "
                f"{symbol}: {e}"
            )

    return prices


# --------------------------------------------------
# CoinGecko fallback
# --------------------------------------------------

def get_coingecko_prices(symbols):
    if not symbols:
        return {}

    coin_ids = []

    for symbol in symbols:
        symbol = symbol.upper()

        if symbol in COINGECKO_IDS:
            coin_ids.append(
                COINGECKO_IDS[symbol]
            )
        else:
            print(
                f"No CoinGecko mapping for {symbol}"
            )

    if not coin_ids:
        return {}

    url = "https://api.coingecko.com/api/v3/simple/price"

    params = {
        "ids": ",".join(sorted(set(coin_ids))),
        "vs_currencies": "usd"
    }

    try:
        r = requests.get(
            url,
            params=params,
            timeout=15
        )

        print(
            f"CoinGecko response: "
            f"{r.status_code} {r.text}"
        )

        r.raise_for_status()

        data = r.json()

        prices = {}

        for symbol in symbols:
            symbol = symbol.upper()

            coin_id = COINGECKO_IDS.get(
                symbol
            )

            if (
                coin_id
                and coin_id in data
                and "usd" in data[coin_id]
            ):
                prices[symbol] = float(
                    data[coin_id]["usd"]
                )

        return prices

    except requests.exceptions.RequestException as e:
        print(
            f"CoinGecko request error: {e}"
        )

    except (ValueError, TypeError, KeyError) as e:
        print(
            f"CoinGecko data error: {e}"
        )

    except Exception as e:
        print(
            f"Unexpected CoinGecko error: {e}"
        )

    return {}


# --------------------------------------------------
# Two-stage price system
# --------------------------------------------------

def get_prices(symbols):
    if not symbols:
        return {}

    symbols = [
        symbol.upper()
        for symbol in symbols
        if symbol
    ]

    # Stage 1: Binance Futures

    prices = get_binance_futures_prices(
        symbols
    )

    # Find missing symbols

    missing_symbols = [
        symbol
        for symbol in symbols
        if symbol not in prices
    ]

    # Stage 2: CoinGecko fallback

    if missing_symbols:

        print(
            "Binance Futures unavailable for: "
            f"{missing_symbols}"
        )

        print(
            "Trying CoinGecko fallback..."
        )

        fallback_prices = (
            get_coingecko_prices(
                missing_symbols
            )
        )

        for symbol, price in (
            fallback_prices.items()
        ):
            prices[symbol] = price

            print(
                f"CoinGecko fallback price for "
                f"{symbol}: {price}"
            )

    return prices


def send_bale_message(
    text,
    with_menu=True
):
    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        return

    url = (
        f"https://tapi.bale.ai/"
        f"bot{BALE_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": BALE_CHAT_ID,
        "text": text
    }

    if with_menu:
        payload["reply_markup"] = (
            MENU_KEYBOARD
        )

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=15
        )

        print(
            "Bale send:",
            r.status_code,
            r.text
        )

    except Exception as e:
        print(
            "Error sending Bale message:",
            e
        )


def send_ntfy_message(text):
    if not NTFY_TOPIC:
        return

    try:
        r = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=text.encode("utf-8"),
            timeout=15
        )

        print(
            "ntfy send:",
            r.status_code
        )

    except Exception as e:
        print(
            "Error sending ntfy message:",
            e
        )


def get_bale_updates(offset):
    if not BALE_BOT_TOKEN:
        return []

    url = (
        f"https://tapi.bale.ai/"
        f"bot{BALE_BOT_TOKEN}/getUpdates"
    )

    params = (
        {"offset": offset + 1}
        if offset
        else {}
    )

    try:
        r = requests.get(
            url,
            params=params,
            timeout=15
        )

        r.raise_for_status()

        return r.json().get(
            "result",
            []
        )

    except Exception as e:
        print(
            "Error getting Bale updates:",
            e
        )

        return []


def format_price(p):
    return (
        str(int(p))
        if p == int(p)
        else str(p)
    )


def parse_alert_command(text):
    parts = text.strip().split()

    if len(parts) != 2:
        return None

    symbol = parts[0].strip().upper()

    if not symbol.endswith("USDT"):
        return None

    try:
        price = float(
            parts[1].replace(",", "")
        )

    except ValueError:
        return None

    return symbol, price


def numbered_alerts_list(state):
    alerts = state.get(
        "alerts",
        {}
    )

    if not alerts:
        return (
            "هیچ آلارم فعالی ندارید.",
            []
        )

    ordered_ids = list(
        alerts.keys()
    )

    lines = [
        "📋 آلارم‌های فعال:"
    ]

    for i, aid in enumerate(
        ordered_ids,
        start=1
    ):

        a = alerts[aid]

        status = (
            "✅ ارسال شده"
            if a["triggered"]
            else
            "⏳ در انتظار"
        )

        arrow = (
            "بالای"
            if a["direction"] == "above"
            else
            "زیر"
        )

        symbol = a.get(
            "symbol",
            a.get("coin", "")
        )

        lines.append(
            f"{i}. {symbol} {arrow} "
            f"{a['price']} — {status}"
        )

    return (
        "\n".join(lines),
        ordered_ids
    )


def add_alert(
    state,
    symbol,
    target_price
):

    prices = get_prices(
        [symbol]
    )

    if symbol not in prices:
        return (
            f"❌ قیمت {symbol} "
            f"در Binance Futures و "
            f"CoinGecko پیدا نشد."
        )

    current_price = prices[
        symbol
    ]

    direction = (
        "above"
        if target_price >= current_price
        else
        "below"
    )

    alert_id = (
        f"{symbol}_{direction}_"
        f"{format_price(target_price)}"
    )

    state["alerts"][alert_id] = {
        "symbol": symbol,
        "direction": direction,
        "price": target_price,
        "triggered": False,
    }

    arrow = (
        "بالاتر رفت از"
        if direction == "above"
        else
        "پایین‌تر آمد از"
    )

    return (
        f"✅ آلارم ثبت شد\n"
        f"{symbol}: وقتی قیمت {arrow} "
        f"{format_price(target_price)} دلار\n"
        f"(قیمت فعلی: "
        f"{format_price(current_price)})"
    )


def process_commands(state):

    updates = get_bale_updates(
        state.get(
            "last_update_id",
            0
        )
    )

    for update in updates:

        state["last_update_id"] = (
            update["update_id"]
        )

        message = update.get(
            "message"
        )

        if (
            not message
            or "text" not in message
        ):
            continue

        text = message[
            "text"
        ].strip()

        # ------------------------------------------
        # Start / Menu
        # ------------------------------------------

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

        # ------------------------------------------
        # Add alert
        # ------------------------------------------

        if text == "➕ افزودن آلارم":

            state["mode"] = (
                "awaiting_add"
            )

            send_bale_message(
                "نماد ارز و قیمت رو بفرستید.\n"
                "مثال: BTCUSDT 100000"
            )

            continue

        # ------------------------------------------
        # List alerts
        # ------------------------------------------

        if text == "📋 لیست آلارم‌ها":

            state["mode"] = None

            list_text, _ = (
                numbered_alerts_list(
                    state
                )
            )

            send_bale_message(
                list_text
            )

            continue

        # ------------------------------------------
        # Delete one alert
        # ------------------------------------------

        if text == "🗑 حذف آلارم":

            list_text, ordered_ids = (
                numbered_alerts_list(
                    state
                )
            )

            if not ordered_ids:

                state["mode"] = None

                send_bale_message(
                    "هیچ آلارمی برای حذف وجود نداره."
                )

            else:

                state["mode"] = (
                    "awaiting_delete"
                )

                state["delete_order"] = (
                    ordered_ids
                )

                send_bale_message(
                    list_text +
                    "\n\nشماره‌ی آلارمی که می‌خواید "
                    "حذف بشه رو بفرستید:"
                )

            continue

        # ------------------------------------------
        # Delete all alerts
        # ------------------------------------------

        if text == "🗑 حذف همه آلارم‌ها":

            if not state.get(
                "alerts"
            ):

                state["mode"] = None

                send_bale_message(
                    "هیچ آلارمی برای حذف وجود نداره."
                )

            else:

                state["mode"] = (
                    "awaiting_delete_all"
                )

                send_bale_message(
                    "⚠️ مطمئن هستید که می‌خواهید "
                    "همه آلارم‌ها حذف شوند؟\n\n"
                    "برای تأیید بنویسید:\n"
                    "✅ بله، حذف همه\n\n"
                    "برای لغو بنویسید:\n"
                    "❌ انصراف"
                )

            continue

        # ------------------------------------------
        # Confirm delete all
        # ------------------------------------------

        if state.get(
            "mode"
        ) == "awaiting_delete_all":

            if text in (
                "✅ بله، حذف همه",
                "بله",
                "بله حذف همه",
                "تایید",
                "تأیید"
            ):

                count = len(
                    state.get(
                        "alerts",
                        {}
                    )
                )

                state["alerts"] = {}

                state["mode"] = None

                state["delete_order"] = []

                send_bale_message(
                    f"✅ همه آلارم‌ها حذف شدند.\n"
                    f"تعداد آلارم‌های حذف‌شده: {count}"
                )

            elif text in (
                "❌ انصراف",
                "انصراف",
                "لغو"
            ):

                state["mode"] = None

                state["delete_order"] = []

                send_bale_message(
                    "❌ حذف همه آلارم‌ها لغو شد."
                )

            else:

                send_bale_message(
                    "لطفاً یکی از این دو گزینه را بفرستید:\n\n"
                    "✅ بله، حذف همه\n"
                    "❌ انصراف"
                )

            continue

        # ------------------------------------------
        # Delete one - number selection
        # ------------------------------------------

        if state.get(
            "mode"
        ) == "awaiting_delete":

            ordered_ids = state.get(
                "delete_order",
                []
            )

            choice = text.strip()

            if (
                choice.isdigit()
                and
                1 <= int(choice)
                <= len(ordered_ids)
            ):

                target_id = (
                    ordered_ids[
                        int(choice) - 1
                    ]
                )

                if target_id in state.get(
                    "alerts",
                    {}
                ):

                    del state[
                        "alerts"
                    ][target_id]

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
                    "لطفاً فقط شماره‌ی آلارم رو "
                    "بفرستید (مثلاً: 1)"
                )

            continue

        # ------------------------------------------
        # Parse new alert
        # ------------------------------------------

        parsed = parse_alert_command(
            text
        )

        if parsed is None:

            send_bale_message(
                "متوجه نشدم 🙁\n"
                "فرمت صحیح:\n"
                "نماد ارز قیمت\n\n"
                "مثال:\n"
                "BTCUSDT 100000"
            )

            continue

        symbol, target_price = (
            parsed
        )

        state["mode"] = None

        send_bale_message(
            add_alert(
                state,
                symbol,
                target_price
            )
        )


def check_alerts(state):

    alerts = state.get(
        "alerts",
        {}
    )

    if not alerts:
        return

    symbols = list({
        a.get(
            "symbol",
            a.get("coin")
        )
        for a in alerts.values()
    })

    prices = get_prices(
        symbols
    )

    for alert in alerts.values():

        if alert["triggered"]:
            continue

        symbol = alert.get(
            "symbol",
            alert.get("coin")
        )

        if symbol not in prices:
            continue

        current_price = prices[
            symbol
        ]

        direction = alert[
            "direction"
        ]

        target_price = alert[
            "price"
        ]

        triggered = (
            (
                direction == "above"
                and
                current_price >= target_price
            )
            or
            (
                direction == "below"
                and
                current_price <= target_price
            )
        )

        if triggered:

            arrow = (
                "بالاتر رفت از"
                if direction == "above"
                else
                "پایین‌تر آمد از"
            )

            message = (
                f"🔔 آلارم قیمت\n"
                f"ارز: {symbol}\n"
                f"قیمت فعلی: "
                f"{format_price(current_price)}\n"
                f"قیمت {arrow} "
                f"{format_price(target_price)}"
            )

            send_bale_message(
                message
            )

            send_ntfy_message(
                message
            )

            alert["triggered"] = True


def main():

    state = load_state()

    process_commands(
        state
    )

    check_alerts(
        state
    )

    save_state(
        state
    )


if __name__ == "__main__":
    main()

