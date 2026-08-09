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
    for path, params in (
        ("/api/author/stats/author/v0/", {"aid": "2503", "app_name": "muye_novel", "book_id": book_id}),
        ("/api/author/stats/author/v0/", {"aid": "2503", "app_name": "muye_novel"}),
    ):
        status, body = get(path, params)
        print("=====", path, params.get("book_id", "no-book"), status)
        print(body[:1200])
        print()


if __name__ == "__main__":
    main()
