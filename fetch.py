import json
data = {"hello": "world"}
open("data.json", "w").write(json.dumps(data))
print("ok")
