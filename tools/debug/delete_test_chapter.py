import json
import os
import urllib.parse
import urllib.request

BASE = "https://fanqienovel.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
ENV = r"C:\Users\Administrator\.n8n\.env"


def load_env():
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def post(path, params):
    req = urllib.request.Request(
        BASE + path,
        data=urllib.parse.urlencode(params).encode(),
        method="POST",
        headers={
            "Cookie": os.environ["FANQIE_COOKIE"],
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE,
            "Referer": BASE + "/main/writer/",
            "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF_TOKEN"],
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
    )
    r = urllib.request.urlopen(req, timeout=20)
    return r.status, r.read().decode()


def main():
    load_env()
    book_id = os.environ["FANQIE_BOOK_ID"]
    item_id = os.environ["FANQIE_ITEM_ID"]
    for is_draft in ("0", "1"):
        status, body = post(
            "/api/author/delete_article/v1",
            {"book_id": book_id, "item_id": item_id, "is_draft": is_draft},
        )
        print("is_draft=", is_draft, "status:", status)
        print("body:", body[:600])


if __name__ == "__main__":
    main()
