import urllib.request
import json

req = urllib.request.Request("http://127.0.0.1:8000/api/dashboard")
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    trend_day = data.get("trend_day", [])
    print(f"Total trend_day entries: {len(trend_day)}")
    for x in trend_day:
        print(f"  {x.get('label')}: inspected={x.get('inspected')}, rejected={x.get('rejected')}")
