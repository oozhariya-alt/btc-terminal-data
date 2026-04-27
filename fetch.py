import json, requests
from datetime import datetime, timezone
H = {"User-Agent": "Mozilla/5.0"}
B = "https://query1.finance.yahoo.com/v8/finance/chart/"
SYMS = [("spx", "^GSPC"), ("nasdaq", "^IXIC"), ("vix", "^VIX"), ("us10y", "^TNX"),
("gold", "GC=F"), ("oil", "CL=F"), ("ibit", "IBIT"), ("xlk", "XLK"), ("xlu", "XLU")]
raws = {k: requests.get(B+s+"?range=1mo&interval=1d", headers=H,
timeout=15).json()["chart"]["result"][0] for k, s in SYMS}
tradfi = {k: {"value": round(r["meta"]["regularMarketPrice"], 2), "change_30d_pct":
round((r["meta"]["regularMarketPrice"] / next(c for c in
r["indicators"]["quote"][0]["close"] if c) - 1) * 100, 2)} for k, r in raws.items()}
data = {"tradfi": tradfi, "updated_at": datetime.now(timezone.utc).isoformat()}
open("data.json", "w").write(json.dumps(data, indent=2))
print(tradfi)
