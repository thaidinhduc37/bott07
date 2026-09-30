"""Gọi /api/chat/modes và /api/chat/courses để xác nhận GIAOTRINH ready. Xóa sau."""
import json
import urllib.request

API = "http://localhost:5000/api"
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


def get(path, cookie):
    req = urllib.request.Request(API + path, headers={"Cookie": cookie})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


_, setc = post("/auth/login", {"email": creds["username"], "password": creds["password"]})
cookie = setc.split(";")[0]
print("login OK, cookie:", cookie[:25] + "...")
print("modes:", json.dumps(get("/chat/modes", cookie), ensure_ascii=False))
print("courses:", json.dumps(get("/chat/courses", cookie), ensure_ascii=False))
