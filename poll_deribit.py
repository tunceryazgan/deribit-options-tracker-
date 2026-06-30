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
BASE_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
TIMEOUT = 20


def fetch(currency):
    url = f"{BASE_URL}?currency={currency}&kind=option"
    req = urllib.request.Request(url, headers={"User-Agent": "deribit-options-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_instrument(name):
    """Sadece vanilya call/put kontratlarini ayikla; spread/strangle gibi
    kombinasyon enstrumanlarini (orn. SOL-CS-..., SOL-STRG-...) eler."""
    parts = name.split("-")
    if len(parts) != 4:
        return None
    _cur, expiry, strike, opt_type = parts
    if opt_type not in ("C", "P"):
        return None
    try:
        strike_f = float(strike)
    except ValueError:
        return None
    return {"expiry": expiry, "type": opt_type, "strike": strike_f}


def summarize(currency):
    data = fetch(currency)
    if data.get("error"):
        raise RuntimeError(data["error"].get("message", "unknown API error"))

    rows = []
    for r in data.get("result", []):
        parsed = parse_instrument(r["instrument_name"])
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

    top_contracts = sorted(rows, key=lambda x: x["volume_usd"], reverse=True)[:10]

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

    for asset in ASSETS:
        try:
            snapshot["assets"][asset] = summarize(asset)
        except Exception as exc:  # noqa: BLE001 - tek varliktaki hata digerini etkilemesin
            snapshot["assets"][asset] = {"currency": asset, "error": str(exc)}

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
