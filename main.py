import os
import requests
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHANNEL", "")

BASE_URL = "https://api.binance.com/api/v3/klines"

PAIRS = [
    {"symbol": "BTCUSDT"},
    {"symbol": "ETHUSDT"},
    {"symbol": "BNBUSDT"},
    {"symbol": "SOLUSDT"},
    {"symbol": "XRPUSDT"},
]

# ─────────────────────────────────────────────
# DATA FETCH (BINANCE)
# ─────────────────────────────────────────────
def get_candles(symbol, interval="15m", limit=100):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        r = requests.get(BASE_URL, params=params, timeout=10)
        data = r.json()

        if not isinstance(data, list):
            print(f"API error {symbol}: {data}")
            return None

        if len(data) == 0:
            print(f"No data {symbol}")
            return None

        closes = []
        highs = []
        lows = []
        volumes = []

        for c in data:
            if len(c) < 6:
                continue

            closes.append(float(c[4]))
            highs.append(float(c[2]))
            lows.append(float(c[3]))
            volumes.append(float(c[5]))

        if len(closes) < 50:
            print(f"Not enough data {symbol}")
            return None

        return {
            "close": closes,
            "high": highs,
            "low": lows,
            "volume": volumes
        }

    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None
# ─────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────
def ema(data, period):
    k = 2 / (period + 1)
    result = [data[0]]
    for price in data[1:]:
        result.append(price * k + result[-1] * (1 - k))
    return result

def atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    return sum(trs[-period:]) / period if len(trs) >= period else trs[-1]

# ─────────────────────────────────────────────
# LOGIC HELPERS
# ─────────────────────────────────────────────
def is_sideways(e20, e30):
    return abs(e20[-1] - e30[-1]) < (e20[-1] * 0.001)

def high_volume(volumes):
    avg = sum(volumes[-20:]) / 20
    return volumes[-1] > avg * 1.5

def break_of_structure(closes):
    return closes[-1] > max(closes[-10:-1]) or closes[-1] < min(closes[-10:-1])

def liquidity_grab(highs, lows):
    return highs[-1] > max(highs[-5:-1]) or lows[-1] < min(lows[-5:-1])

def trend_direction(e5, e10, e20, e30):
    if e5[-1] > e10[-1] > e20[-1] > e30[-1]:
        return "UP"
    elif e5[-1] < e10[-1] < e20[-1] < e30[-1]:
        return "DOWN"
    return "NONE"

# ─────────────────────────────────────────────
# MULTI TF
# ─────────────────────────────────────────────
def get_multi_tf(symbol):
    c15 = get_candles(symbol, "15m")
    c1h = get_candles(symbol, "1h")
    if not c15 or not c1h:
        return None, None
    return c15, c1h

# ─────────────────────────────────────────────
# ANALYZE
# ─────────────────────────────────────────────
def analyze(pair):

    c15, c1h = get_multi_tf(pair["symbol"])
    if not c15 or not c1h:
        return None

    closes = c15["close"]
    highs  = c15["high"]
    lows   = c15["low"]
    volumes = c15["volume"]

    e5  = ema(closes, 5)
    e10 = ema(closes, 10)
    e20 = ema(closes, 20)
    e30 = ema(closes, 30)

    ht_closes = c1h["close"]
    ht_e20 = ema(ht_closes, 20)
    ht_e30 = ema(ht_closes, 30)

    ht_trend = "UP" if ht_e20[-1] > ht_e30[-1] else "DOWN"

    if is_sideways(e20, e30):
        return None

    if not high_volume(volumes):
        return None

    if not break_of_structure(closes):
        return None

    trend = trend_direction(e5, e10, e20, e30)

    if trend == "NONE" or trend != ht_trend:
        return None

    p = closes[-1]
    liq = liquidity_grab(highs, lows)

    atr_v = atr(highs, lows, closes)
    mode = "SCALP" if atr_v < p * 0.005 else "SWING"

    if trend == "UP":
        sl = round(min(lows[-5:]), 2)
        tp1 = round(p + (p - sl) * 1.5, 2)
        tp2 = round(p + (p - sl) * 3.0, 2)

        if liq:
            tp2 = round(p + (p - sl) * 4.0, 2)

        direction = "BUY"

    else:
        sl = round(max(highs[-5:]), 2)
        tp1 = round(p - (sl - p) * 1.5, 2)
        tp2 = round(p - (sl - p) * 3.0, 2)

        if liq:
            tp2 = round(p - (sl - p) * 4.0, 2)

        direction = "SELL"

    return {
        "pair": pair["symbol"],
        "direction": direction,
        "entry": round(p, 2),
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "mode": mode,
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(signal):

    arrow = "🟢" if signal["direction"] == "BUY" else "🔴"

    msg = (
        f"{arrow} *{signal['pair']} — {signal['direction']}*\n\n"
        f"⚡ Mode: {signal['mode']}\n"
        f"📍 Entry: `{signal['entry']}`\n"
        f"✅ TP1: `{signal['tp1']}`\n"
        f"✅ TP2: `{signal['tp2']}`\n"
        f"❌ SL: `{signal['sl']}`\n\n"
        f"⏰ {signal['time']}\n"
        f"🔥 Binance SMC Signal"
    )

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

    try:
        requests.post(url, json={
            "chat_id": TG_CHAT,
            "text": msg,
            "parse_mode": "Markdown"
        })
        print(f"Sent: {signal['pair']} {signal['direction']}")
    except Exception as e:
        print(e)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():

    print("🚀 Binance Signal Bot Running")

    for pair in PAIRS:
        print(f"Checking {pair['symbol']}...")

        signal = analyze(pair)

        if signal:
            print(f"SIGNAL: {signal['direction']}")
            send_telegram(signal)
        else:
            print("No signal")

if __name__ == "__main__":
    main()
