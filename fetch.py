import json, os, requests
from datetime import datetime, timezone

H = {"User-Agent": "Mozilla/5.0"}
B = "https://query1.finance.yahoo.com/v8/finance/chart/"
SYMS = [
    ("spx", "^GSPC"), ("nasdaq", "^IXIC"), ("vix", "^VIX"), ("us10y", "^TNX"),
    ("dxy", "DX-Y.NYB"),
    ("gold", "GC=F"), ("silver", "SI=F"), ("oil", "CL=F"), ("copper", "HG=F"),
    ("platinum", "PL=F"), ("palladium", "PA=F"), ("natgas", "NG=F"),
    ("ibit", "IBIT"), ("fbtc", "FBTC"), ("bitb", "BITB"),
    ("xlk", "XLK"), ("xlf", "XLF"), ("xle", "XLE"), ("xlu", "XLU"), ("xlv", "XLV"),
    ("btc_fut", "BTC=F"),
]

# Phase 4 (2026-05-01): индикаторы, для которых пишем series60d (для frontend-корреляций)
SERIES_KEYS = {"spx", "nasdaq", "vix", "us10y", "dxy", "gold", "oil"}

FRED = "https://api.stlouisfed.org/fred/series/observations"
FRED_KEY = os.environ.get("FRED_API_KEY", "")

# Phase 4 (2026-05-01): CoinGecko Demo API + on-chain MVRV/NUPL
CG_KEY = os.environ.get("CG_API_KEY", "")
CG_BASE = "https://api.coingecko.com/api/v3"


def fetch_yahoo(symbol, with_series=False):
    # 3mo даёт ~64 торговых дня, что покрывает 60-дневный Pearson + запас на weekend gaps
    yrange = "3mo" if with_series else "1mo"
    r = requests.get(B + symbol + f"?range={yrange}&interval=1d", headers=H, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    cur = res["meta"]["regularMarketPrice"]
    closes = res["indicators"]["quote"][0]["close"]
    first = next(c for c in closes if c)

    out = {
        "value": round(cur, 2),
        "change_30d_pct": round((cur / first - 1) * 100, 2),
    }

    if with_series:
        ts = res.get("timestamp", [])
        series = []
        for t, c in zip(ts, closes):
            if c is None:
                continue
            d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
            series.append({"date": d, "close": round(c, 4)})
        # Берём последние 60 торговых точек (если меньше — все доступные)
        out["series60d"] = series[-60:]

    return out


def fetch_fred_series(series_id, days_back=400):
    if not FRED_KEY:
        raise RuntimeError("FRED_API_KEY not set")
    params = {
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": days_back,
    }
    r = requests.get(FRED, params=params, timeout=15)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    pts = []
    for o in obs:
        try:
            v = float(o["value"])
        except (ValueError, KeyError):
            continue
        pts.append((o["date"], v))
    return pts  # newest first


def fred_fed_rate():
    pts = fetch_fred_series("DFF", days_back=60)
    if not pts:
        return None
    today_val = pts[0][1]
    target = _date_30d_ago(pts[0][0])
    val_30d = None
    for d, v in pts:
        if d <= target:
            val_30d = v
            break
    out = {"value": round(today_val, 2)}
    if val_30d is not None and val_30d != 0:
        out["change_30d_pct"] = round((today_val / val_30d - 1) * 100, 2)
    return out


def fred_m2_yoy():
    pts = fetch_fred_series("M2SL", days_back=400)
    if len(pts) < 2:
        return None
    today_val = pts[0][1]
    target = _date_year_ago(pts[0][0])
    val_yr = None
    for d, v in pts:
        if d <= target:
            val_yr = v
            break
    if val_yr is None or val_yr == 0:
        return None
    yoy = (today_val / val_yr - 1) * 100
    return {"value": round(yoy, 2)}


def _date_30d_ago(iso_date):
    y, m, d = map(int, iso_date.split("-"))
    from datetime import date, timedelta
    return (date(y, m, d) - timedelta(days=30)).isoformat()


def _date_year_ago(iso_date):
    y, m, d = map(int, iso_date.split("-"))
    return f"{y - 1:04d}-{m:02d}-{d:02d}"


# ── COINGECKO (Phase 4) ────────────────────────────────────────────
def cg_get(path, params=None):
    headers = dict(H)
    if CG_KEY:
        headers["x-cg-demo-api-key"] = CG_KEY
    r = requests.get(CG_BASE + path, params=params or {}, headers=headers, timeout=25)
    r.raise_for_status()
    return r.json()


def _safe_float(x):
    try:
        v = float(x)
        return v if v == v else None  # NaN check
    except (TypeError, ValueError):
        return None


def fetch_cg_coin(coin_id):
    d = cg_get(f"/coins/{coin_id}", {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
    })
    md = d.get("market_data", {}) or {}
    return {
        "price": _safe_float((md.get("current_price") or {}).get("usd")),
        "ath": _safe_float((md.get("ath") or {}).get("usd")),
        "ath_date": (md.get("ath_date") or {}).get("usd"),
        "ath_change_pct": _safe_float((md.get("ath_change_percentage") or {}).get("usd")),
        "atl": _safe_float((md.get("atl") or {}).get("usd")),
        "mcap": _safe_float((md.get("market_cap") or {}).get("usd")),
        "supply": _safe_float(md.get("circulating_supply")),
        "total_supply": _safe_float(md.get("total_supply")),
        "max_supply": _safe_float(md.get("max_supply")),
        "fdv": _safe_float((md.get("fully_diluted_valuation") or {}).get("usd")),
        "vol_24h": _safe_float((md.get("total_volume") or {}).get("usd")),
        "change_24h_pct": _safe_float(md.get("price_change_percentage_24h")),
        "change_7d_pct": _safe_float(md.get("price_change_percentage_7d")),
        "change_30d_pct": _safe_float(md.get("price_change_percentage_30d")),
        "change_1y_pct": _safe_float(md.get("price_change_percentage_1y")),
    }


def fetch_cg_global():
    d = (cg_get("/global") or {}).get("data", {}) or {}
    return {
        "total_mcap": _safe_float((d.get("total_market_cap") or {}).get("usd")),
        "total_volume": _safe_float((d.get("total_volume") or {}).get("usd")),
        "btc_dominance": _safe_float((d.get("market_cap_percentage") or {}).get("btc")),
        "eth_dominance": _safe_float((d.get("market_cap_percentage") or {}).get("eth")),
        "active_cryptos": d.get("active_cryptocurrencies"),
        "mcap_change_24h_pct": _safe_float(d.get("market_cap_change_percentage_24h_usd")),
    }


def fetch_cg_treasury():
    d = cg_get("/companies/public_treasury/bitcoin") or {}
    return {
        "total_holdings_btc": _safe_float(d.get("total_holdings")),
        "total_value_usd": _safe_float(d.get("total_value_usd")),
        "market_cap_dominance": _safe_float(d.get("market_cap_dominance")),
        "companies_count": len(d.get("companies", []) or []),
    }


def fetch_cg_categories(top_n=30):
    d = cg_get("/coins/categories") or []
    if not isinstance(d, list):
        return None
    out = []
    for c in d[:top_n]:
        out.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "mcap": _safe_float(c.get("market_cap")),
            "change_24h_pct": _safe_float(c.get("market_cap_change_24h")),
            "volume_24h": _safe_float(c.get("volume_24h")),
        })
    return out


def fetch_cg_btc_30d():
    d = cg_get("/coins/bitcoin/market_chart", {
        "vs_currency": "usd", "days": 30, "interval": "daily",
    }) or {}
    prices = d.get("prices", []) or []
    return [{"ts": int(p[0] / 1000), "price": round(p[1], 2)} for p in prices if p and len(p) == 2]


# ── ON-CHAIN MVRV/NUPL/Realized Price (Phase 4) ────────────────────
# bitcoin-data.com — open community API, no key required.
ONCHAIN_BASE = "https://bitcoin-data.com/api/v1"


def _onchain_get(path):
    r = requests.get(ONCHAIN_BASE + path, headers=H, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_onchain_metric(path, value_key):
    """Универсальный ридер: /<metric>/last → {<value_key>:..., d:'YYYY-MM-DD'}"""
    try:
        d = _onchain_get(path)
        val = _safe_float(d.get(value_key))
        date = d.get("d") or d.get("date")
        return {"value": val, "date": date}
    except Exception as e:
        print(f"[onchain {path} fail] {e}")
        return None


# ── EXECUTE ────────────────────────────────────────────────────────
tradfi = {}
for k, s in SYMS:
    try:
        tradfi[k] = fetch_yahoo(s, with_series=(k in SERIES_KEYS))
    except Exception as e:
        print(f"[yahoo fail] {k} ({s}): {e}")

try:
    fr = fred_fed_rate()
    if fr:
        tradfi["fed_rate"] = fr
except Exception as e:
    print(f"[fred fed_rate fail] {e}")

try:
    m2 = fred_m2_yoy()
    if m2:
        tradfi["m2_yoy"] = m2
except Exception as e:
    print(f"[fred m2_yoy fail] {e}")

# CoinGecko
cg = {}
for name, fn in [
    ("btc", lambda: fetch_cg_coin("bitcoin")),
    ("eth", lambda: fetch_cg_coin("ethereum")),
    ("global", fetch_cg_global),
    ("treasury", fetch_cg_treasury),
    ("categories", fetch_cg_categories),
    ("btc_30d", fetch_cg_btc_30d),
]:
    try:
        cg[name] = fn()
    except Exception as e:
        print(f"[cg {name} fail] {e}")

# On-chain
onchain = {}
for key, path, val_key in [
    ("mvrv", "/mvrv/last", "mvrv"),
    ("mvrv_zscore", "/mvrv-zscore/last", "mvrvZscore"),
    ("nupl", "/nupl/last", "nupl"),
    ("realized_price", "/realized-price/last", "realizedPrice"),
    ("realized_cap", "/realized-cap/last", "realizedCap"),
    ("puell", "/puell-multiple/last", "puellMultiple"),
    ("active_addresses", "/addresses-active-count/last", "activeAddresses"),
    ("sopr", "/sopr/last", "sopr"),
]:
    rec = fetch_onchain_metric(path, val_key)
    if rec and rec.get("value") is not None:
        onchain[key] = rec["value"]
        # Сохраняем дату последней метрики (одну общую — у всех источников совпадает)
        if rec.get("date"):
            onchain.setdefault("date", rec["date"])

whales = {"count_1k_plus": None}
data = {
    "tradfi": tradfi,
    "whales": whales,
    "cg": cg,
    "onchain": onchain,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
open("data.json", "w").write(json.dumps(data, indent=2))
print(f"[ok] wrote {len(tradfi)} tradfi indicators")
n_series = sum(1 for v in tradfi.values() if isinstance(v, dict) and "series60d" in v)
print(f"[ok] series60d for {n_series} indicators")
print(f"[ok] cg sections: {sorted(cg.keys())}")
print(f"[ok] onchain keys: {sorted(onchain.keys())}")
