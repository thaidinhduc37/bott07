"""Kiểm tra Gemini key + model. Xóa sau."""
import json
import urllib.request

key = "AIzaSyA7lj479cAMi30JfUabNUyn6mkWO6xq8_o"
for model in ("gemini-3.1-flash-lite", "gemini-2.5-flash"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    data = json.dumps({"contents": [{"parts": [{"text": "Reply with the single word: pong"}]}]}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        body = r.read().decode()
        print(model, "-> OK", r.status, body[:150])
    except Exception as e:
        print(model, "-> FAIL", getattr(e, "code", e))
        try:
            print("   ", e.read().decode()[:300])
        except Exception:
            pass
