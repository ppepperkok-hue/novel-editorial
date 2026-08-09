import json
import os
import urllib.parse
import urllib.request

BASE = "https://fanqienovel.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def post(path, params):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={
            "Cookie": os.environ["FANQIE_COOKIE"],
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE,
            "Referer": BASE + "/main/writer/",
            "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF"],
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
    )
    r = urllib.request.urlopen(req, timeout=20)
    return r.status, r.read().decode()


params = {
    "book_id": os.environ["FANQIE_BOOK_ID"],
    "need_reuse": "0",
    "aid": "2503",
    "app_name": "muye_novel",
}
try:
    status, body = post("/api/author/article/new_article/v0/", params)
    print("status:", status)
    print("body:", body[:1200])
    data = json.loads(body)
    if data.get("code") == 0:
        d = data["data"]
        print("item_id:", d.get("item_id"))
        print("volume_id:", d.get("volume_id"))
        print("volume_data:", str(d.get("volume_data"))[:300])
except Exception as e:
    print("error:", e)
    if hasattr(e, "read"):
        print("resp:", e.read().decode()[:1200])
