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
            "Referer": BASE + "/main/writer/book-info/" + os.environ["FANQIE_BOOK_ID"],
            "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF_TOKEN"],
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
    )
    r = urllib.request.urlopen(req, timeout=20)
    return r.status, r.read().decode()


def main():
    load_env()
    book_id = os.environ["FANQIE_BOOK_ID"]
    params = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_id": book_id,
        "book_name": "破碗提纯：从杂灵根苟到无敌",
        "gender": "1",
        "abstract": "杂灵根弟子李默在宗门杂役房捡到一只会提纯灵物的破碗，从此废柴逆袭，一边装傻苟发育，一边用破碗提纯灵石丹药，从最底层一路苟成无敌强者。",
        "category_id": "259",
        "original_type": "1",
        "label_id_list": "259,257",
        "protagonist_name_1": "林凡",
        "protagonist_name_2": "周平",
    }
    status, body = post("/api/author/book/modify_book/v0/", params)
    print("status:", status)
    print("body:", body[:1200])


if __name__ == "__main__":
    main()
