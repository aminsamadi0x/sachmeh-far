import os, json, requests
token = os.environ["RUBIKA_TOKEN"]
r = requests.post(f"https://botapi.rubika.ir/v3/{token}/getUpdates", json={"limit": 20}, timeout=30)
print(json.dumps(r.json(), ensure_ascii=False, indent=2))
