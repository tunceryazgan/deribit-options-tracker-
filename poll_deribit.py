"""
Deribit SOL & HYPE options poller.

GitHub Actions bu scripti dakikalar arayla calistirir (Deribit Turkiye'den
erisilemedigi icin, bu islem GitHub'in ABD/AB sunucularinda yapilir).
Cikti olarak:
  - data/latest.json   -> en guncel anlik durum (her iki varlik icin)
  - data/history.csv   -> zaman serisi (trend grafikleri icin satir biriktirir)
uretir.
"""

import csv
import json
import os
import urllib.request
from datetime import datetime, timezone

ASSETS = ["SOL", "HYPE"]
SUMMARY_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
TRADES_URL = "https://www.deribit.com/api/v2/public/get_last_trades_by_currency"
TIMEOUT = 20
TRADES_FETCH_COUNT = 1000  # Deribit'in tek cagrida verdigi pratik ust sinir
TRADES_KEEP_PER_ASSET = 100
WHALE_MULTIPLIER = 5  # "whale" esigi: bu pencerede ortalama islem buyuklugunun kac kati
TOP_CONTRACTS_LIMIT = 20

# SOL ve HYPE'in yeni USDC-marjinli ("linear") opsiyonlari Deribit'te
# settlement/teminat para birimi USDC altinda listeleniyor; kontrat ismi de
# "SOL_USDC-25DEC26-150-C" / "HYPE_USDC-25DEC26-100-C" seklinde. Bu yuzden
# API'ye dogrudan currency=SOL / currency=HYPE ile sormuyoruz; tek seferde
# currency=USDC kind=option cekip kontrat ismindeki on ekten ayikliyoruz.
QUERY_CURRENCY = "USDC"
ASSET_PREFIX = {"SOL": "SOL_USDC-", "HYPE": "HYPE_USDC-"}


def fetch(url, params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}?{qs}"
    req = urllib.request.Request(full_url, headers={"User-Agent": "deribit-options-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_instrument(name, prefix):
    """Sadece istenen varligin vanilya call/put kontratlarini ayikla.
    Format: SOL_USDC-25DEC26-150-C  ->  base kismi 'SOL_USDC' iceriyor,
    bu yuzden once prefix ile esle, sonra kalan kismi vade/strike/tip olarak
    parse et."""
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]  # "25DEC26-150-C"
    parts = rest.split("-")
    if len(parts) != 3:
        return None
    expiry, strike, opt_type = parts
    if opt_type not in ("C", "P"):
        return None
    try:
        strike_f = float(strike)
    except ValueError:
        return None
    return {"expiry": expiry, "type": opt_type, "strike": strike_f}


def process_trades(currency, trades_data):
    prefix = ASSET_PREFIX[currency]
    trades = []
    for t in trades_data.get("trades", []):
        parsed = parse_instrument(t["instrument_name"], prefix)
        if not parsed:
            continue
        amount = t.get("amount") or 0
        index_price = t.get("index_price")
        # Notional: islem buyuklugunun USD karsiligi (underlying coin adedi x spot fiyat)
        if index_price:
            notional_usd = amount * index_price
        else:
            notional_usd = amount * (t.get("price") or 0) * (index_price or 0)
        trades.append({
            "ts": t.get("timestamp"),
            "instrument": t["instrument_name"],
            "expiry": parsed["expiry"],
            "strike": parsed["strike"],
            "type": parsed["type"],
            "direction": t.get("direction"),
            "price": t.get("price"),
            "iv": t.get("iv"),
            "amount": amount,
            "premium_usd": round((t.get("price") or 0) * amount, 2),
            "notional_usd": round(notional_usd, 2),
            "trade_id": t.get("trade_id"),
        })

    # En yeni once gelsin
    trades.sort(key=lambda x: x["ts"] or 0, reverse=True)
    window = trades[:TRADES_KEEP_PER_ASSET]

    notionals = [t["notional_usd"] for t in window if t["notional_usd"]]
    avg_notional = (sum(notionals) / len(notionals)) if notionals else 0.0
    whale_threshold = avg_notional * WHALE_MULTIPLIER

    buy_notional = sum(t["notional_usd"] for t in window if t["direction"] == "buy")
    sell_notional = sum(t["notional_usd"] for t in window if t["direction"] == "sell")
    total_notional = buy_notional + sell_notional
    buy_pct = (buy_notional / total_notional * 100) if total_notional else 50.0

    iv_values = [t["iv"] for t in window if t.get("iv")]
    latest_iv = window[0]["iv"] if window and window[0].get("iv") else None
    avg_iv = (sum(iv_values) / len(iv_values)) if iv_values else None

    for t in window:
        t["is_whale"] = bool(whale_threshold) and t["notional_usd"] >= whale_threshold

    return {
        "trades": window,
        "stats": {
            "count": len(window),
            "avg_notional": round(avg_notional, 2),
            "whale_threshold": round(whale_threshold, 2),
            "buy_notional": round(buy_notional, 2),
            "sell_notional": round(sell_notional, 2),
            "buy_pct": round(buy_pct, 1),
            "latest_iv": latest_iv,
            "avg_iv": round(avg_iv, 2) if avg_iv is not None else None,
        },
    }


def summarize(currency, usdc_data):
    prefix = ASSET_PREFIX[currency]

    rows = []
    for r in usdc_data.get("result", []):
        parsed = parse_instrument(r["instrument_name"], prefix)
        if not parsed:
            continue
        rows.append({
            **parsed,
            "instrument_name": r["instrument_name"],
            "volume": r.get("volume") or 0,
            "volume_usd": r.get("volume_usd") or 0,
            "oi": r.get("open_interest") or 0,
            "underlying": r.get("underlying_price"),
        })

    total_volume = sum(x["volume"] for x in rows)
    total_usd = sum(x["volume_usd"] for x in rows)
    total_oi = sum(x["oi"] for x in rows)
    call_volume = sum(x["volume"] for x in rows if x["type"] == "C")
    put_volume = sum(x["volume"] for x in rows if x["type"] == "P")
    active_contracts = sum(1 for x in rows if x["volume"] > 0)
    spot_candidates = [x["underlying"] for x in rows if x["underlying"]]
    spot = spot_candidates[0] if spot_candidates else None

    by_expiry = {}
    for x in rows:
        g = by_expiry.setdefault(x["expiry"], {"expiry": x["expiry"], "call": 0.0, "put": 0.0, "usd": 0.0, "oi": 0.0})
        if x["type"] == "C":
            g["call"] += x["volume"]
        else:
            g["put"] += x["volume"]
        g["usd"] += x["volume_usd"]
        g["oi"] += x["oi"]

    by_strike = {}
    for x in rows:
        g = by_strike.setdefault(x["strike"], {"strike": x["strike"], "call_oi": 0.0, "put_oi": 0.0, "call_vol": 0.0, "put_vol": 0.0})
        if x["type"] == "C":
            g["call_oi"] += x["oi"]
            g["call_vol"] += x["volume"]
        else:
            g["put_oi"] += x["oi"]
            g["put_vol"] += x["volume"]

    top_contracts = sorted(rows, key=lambda x: x["volume_usd"], reverse=True)[:TOP_CONTRACTS_LIMIT]

    return {
        "currency": currency,
        "spot": spot,
        "total_volume": total_volume,
        "total_volume_usd": total_usd,
        "total_oi": total_oi,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "active_contracts": active_contracts,
        "by_expiry": sorted(by_expiry.values(), key=lambda g: g["expiry"]),
        "by_strike": sorted(by_strike.values(), key=lambda g: g["strike"]),
        "top_contracts": [
            {
                "instrument": c["instrument_name"],
                "type": c["type"],
                "volume_usd": c["volume_usd"],
                "oi": c["oi"],
            }
            for c in top_contracts
        ],
    }


def main():
    ts = datetime.now(timezone.utc).isoformat()
    snapshot = {"timestamp": ts, "assets": {}}

    try:
        usdc_data = fetch(SUMMARY_URL, {"currency": QUERY_CURRENCY, "kind": "option"})
        if usdc_data.get("error"):
            raise RuntimeError(usdc_data["error"].get("message", "unknown API error"))
    except Exception as exc:  # noqa: BLE001
        for asset in ASSETS:
            snapshot["assets"][asset] = {"currency": asset, "error": str(exc)}
        usdc_data = None

    try:
        trades_data = fetch(TRADES_URL, {
            "currency": QUERY_CURRENCY,
            "kind": "option",
            "count": TRADES_FETCH_COUNT,
            "sorting": "desc",
        })
        if trades_data.get("error"):
            raise RuntimeError(trades_data["error"].get("message", "unknown API error"))
        trades_data = trades_data.get("result", {})
    except Exception as exc:  # noqa: BLE001 - islem akisi patlasa bile ozet veriler gitsin
        trades_data = None
        trades_error = str(exc)
    else:
        trades_error = None

    if usdc_data is not None:
        for asset in ASSETS:
            try:
                snapshot["assets"][asset] = summarize(asset, usdc_data)
            except Exception as exc:  # noqa: BLE001 - tek varliktaki hata digerini etkilemesin
                snapshot["assets"][asset] = {"currency": asset, "error": str(exc)}
                continue

            try:
                if trades_data is not None:
                    trade_info = process_trades(asset, trades_data)
                else:
                    trade_info = {"trades": [], "stats": {}, "error": trades_error}
                snapshot["assets"][asset]["trades"] = trade_info["trades"]
                snapshot["assets"][asset]["trade_stats"] = trade_info["stats"]
            except Exception as exc:  # noqa: BLE001
                snapshot["assets"][asset]["trades"] = []
                snapshot["assets"][asset]["trade_stats"] = {}
                snapshot["assets"][asset]["trades_error"] = str(exc)

    os.makedirs("data", exist_ok=True)

    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    history_path = "data/history.csv"
    is_new = not os.path.exists(history_path)
    with open(history_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "currency", "total_volume_usd", "total_oi", "call_volume", "put_volume", "spot"])
        for asset, d in snapshot["assets"].items():
            if "error" in d:
                continue
            writer.writerow([ts, asset, d["total_volume_usd"], d["total_oi"], d["call_volume"], d["put_volume"], d["spot"]])

    print(f"OK {ts} -> data/latest.json, data/history.csv guncellendi")


if __name__ == "__main__":
    main()
