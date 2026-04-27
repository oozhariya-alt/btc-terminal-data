import json
import requests
from datetime import datetime, timezone
url = "https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?range=1mo&interval=1d"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
res = r.json()["chart"]["result"][0]
spx = res["meta"]["regularMarketPrice"]
data = {"tradfi": {"spx": spx}, "updated_at": datetime.now(timezone.utc).isoformat()}
open("data.json", "w").write(json.dumps(data, indent=2))
print("SPX:", spx)
