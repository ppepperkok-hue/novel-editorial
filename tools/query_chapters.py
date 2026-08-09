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


def get(path, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        BASE + path + "?" + qs,
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
    return r.status, r.read().decode()


def main():
    load_env()
    book_id = os.environ["FANQIE_BOOK_ID"]
    for path, key in (
        ("/api/author/chapter/chapter_list/v1", "chapter_list"),
        ("/api/author/chapter/draft_list/v1/", "draft_list"),
    ):
        status, body = get(
            path,
            {"book_id": book_id, "aid": "2503", "app_name": "muye_novel", "page_index": "0", "page_count": "50"},
        )
        print("=====", path, "status", status)
        try:
            data = json.loads(body)
        except Exception:
            print(body[:500])
            continue
        print("code:", data.get("code"), "message:", data.get("message"))
        if data.get("code") == 0:
            d = data.get("data") or {}
            lst = d.get(key) if isinstance(d, dict) else data.get(key)
            print("count:", len(lst) if lst else 0)
            for it in lst or []:
                print("-", it.get("item_id"), it.get("title"), "status:", it.get("status"), "word_count:", it.get("word_count"), "audit_status:", it.get("audit_status"))
        else:
            print("body:", body[:600])


if __name__ == "__main__":
    main()
