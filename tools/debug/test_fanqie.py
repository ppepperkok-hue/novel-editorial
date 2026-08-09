import json
import os
import urllib.parse
import urllib.request

BASE = "https://fanqienovel.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def headers(csrf):
    return {
        "Cookie": os.environ["FANQIE_COOKIE"],
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": BASE,
        "Referer": BASE + "/main/writer/",
        "X-Secsdk-Csrf-Token": csrf,
    }


def get(path, params, csrf):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}{path}?{qs}", headers=headers(csrf))
    r = urllib.request.urlopen(req, timeout=20)
    return r.status, r.read().decode()


def main():
    csrf = os.environ.get("FANQIE_CSRF", "")
    params = {
        "aid": "2503",
        "app_name": "muye_novel",
        "page_index": "0",
        "page_count": "50",
    }
    try:
        status, body = get("/api/author/book/book_list/v0", params, csrf)
        print("status:", status)
        print("body head:", body[:800])
        data = json.loads(body)
        if data.get("code") == 0:
            books = data.get("data", {})
            lst = books.get("book_list") or books.get("list") or (books if isinstance(books, list) else [])
            print("books found:", len(lst))
            for b in lst:
                print("-", b.get("book_id"), b.get("book_name"), "status:", b.get("creation_status"), b.get("status"))
    except Exception as e:
        print("error:", e)
        if hasattr(e, "read"):
            print("resp:", e.read().decode()[:800])


if __name__ == "__main__":
    main()
