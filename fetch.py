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

whales = {"count_1k_plus": None}
data = {
    "tradfi": tradfi,
    "whales": whales,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
open("data.json", "w").write(json.dumps(data, indent=2))
print(f"[ok] wrote {len(tradfi)} indicators")
n_series = sum(1 for v in tradfi.values() if isinstance(v, dict) and "series60d" in v)
print(f"[ok] series60d for {n_series} indicators")
