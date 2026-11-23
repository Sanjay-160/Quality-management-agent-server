import urllib.request
import json

req = urllib.request.Request("http://127.0.0.1:8000/api/dashboard")
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    print("Trend Week:")
    for x in data.get("trend_week", [])[-6:]:
        print(f"  {x.get('label')}: inspected={x.get('inspected')}, rejected={x.get('rejected')}")
    print("\nTrend Month:")
    for x in data.get("trend_month", []):
        print(f"  {x.get('label')}: inspected={x.get('inspected')}, rejected={x.get('rejected')}")
