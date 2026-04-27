import json, requests
from datetime import datetime, timezone
H = {"User-Agent": "Mozilla/5.0"}
B = "https://query1.finance.yahoo.com/v8/finance/chart/"
SYMS = [("spx", "^GSPC"), ("nasdaq", "^IXIC"), ("vix", "^VIX"), ("us10y", "^TNX"),
("gold", "GC=F")]
tradfi = {k: round(requests.get(B+s+"?range=1mo&interval=1d", headers=H,
timeout=15).json()["chart"]["result"][0]["meta"]["regularMarketPrice"], 2) for k, s in   SYMS}
if tradfi.get("us10y"): tradfi["us10y"] = round(tradfi["us10y"]/10, 2)
data = {"tradfi": tradfi, "updated_at": datetime.now(timezone.utc).isoformat()}
open("data.json", "w").write(json.dumps(data, indent=2))
print(tradfi)
