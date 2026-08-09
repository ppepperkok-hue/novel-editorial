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


def main():
    load_env()
    book_id = os.environ["FANQIE_BOOK_ID"]
    item_id = os.environ["FANQIE_ITEM_ID"]
    qs = urllib.parse.urlencode(
        {"book_id": book_id, "item_id": item_id, "from_source": "0"}
    )
    req = urllib.request.Request(
        BASE + "/api/author/edit_article/v0/?" + qs,
        headers={
            "Cookie": os.environ["FANQIE_COOKIE"],
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE,
            "Referer": BASE + "/main/writer/",
            "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF_TOKEN"],
        },
    )
    r = urllib.request.urlopen(req, timeout=20)
    body = r.read().decode()
    print("body:", body[:1500])
    try:
        d = json.loads(body)
        if d.get("code") == 0:
            data = d["data"]
            content = data.get("content") or ""
            words = len("".join(ch for ch in content if "\u4e00" <= ch <= "\u9fff"))
            print("title:", data.get("title"))
            print("content len:", len(content), "chinese chars:", words)
    except Exception:
        pass


if __name__ == "__main__":
    main()
