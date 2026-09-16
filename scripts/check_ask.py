"""Thử một câu hỏi GIAOTRINH thực tế để xác nhận pipeline trả lời. Xóa sau."""
import json
import urllib.request

API = "http://localhost:4000/api"
creds = json.load(open(r"D:\projects\bott07\test_login.json"))


def post(path, body, cookie=""):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        setc = r.headers.get("Set-Cookie", "")
        return json.loads(r.read().decode()), setc


_, setc = post("/auth/login", {"email": creds["username"], "password": creds["password"]})
cookie = setc.split(";")[0]
res, _ = post(
    "/chat/ask",
    {"question": "Khóa chính trong cơ sở dữ liệu là gì?", "mode": "GIAOTRINH"},
    cookie,
)
m = res["message"]
print("abstained:", m["abstained"])
print("confidence:", m["confidence"], "| threshold:", m["threshold"])
print("grounded:", m["grounded"], "| route:", m["route"])
print("citations:", len(m["citations"]))
print("--- câu trả lời (200 ký tự) ---")
print(m["content"][:200])
