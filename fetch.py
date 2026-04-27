import json, requests
from datetime import datetime, timezone
H = {"User-Agent": "Mozilla/5.0"}
B = "https://query1.finance.yahoo.com/v8/finance/chart/"
SYMS = [("spx", "^GSPC"), ("nasdaq", "^IXIC"), ("vix", "^VIX"), ("us10y", "^TNX"),
("gold", "GC=F"), ("silver", "SI=F"), ("oil", "CL=F"), ("copper", "HG=F"), ("ibit",
"IBIT"), ("fbtc", "FBTC"), ("bitb", "BITB"), ("xlk", "XLK"), ("xlf", "XLF"), ("xle",
"XLE"), ("xlu", "XLU"), ("xlv", "XLV"), ("btc_fut", "BTC=F")]
raws = {k: requests.get(B+s+"?range=1mo&interval=1d", headers=H,
timeout=15).json()["chart"]["result"][0] for k, s in SYMS}
tradfi = {k: {"value": round(r["meta"]["regularMarketPrice"], 2), "change_30d_pct":
round((r["meta"]["regularMarketPrice"] / next(c for c in
r["indicators"]["quote"][0]["close"] if c) - 1) * 100, 2)} for k, r in raws.items()}
try: wh = requests.get("https://community-api.coinmetrics.io/v4/timeseries/asset-metri  cs?assets=btc&metrics=AdrBalNtv1KCnt&page_size=1", headers=H, timeout=15).json(); cnt
= int(float(wh["data"][0]["AdrBalNtv1KCnt"]))
except: cnt = None
whales = {"count_1k_plus": cnt}
data = {"tradfi": tradfi, "whales": whales, "updated_at":
datetime.now(timezone.utc).isoformat()}
open("data.json", "w").write(json.dumps(data, indent=2))
print(tradfi, whales)
