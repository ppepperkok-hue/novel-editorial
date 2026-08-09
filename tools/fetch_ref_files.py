import json
import time
import urllib.request
from pathlib import Path

OUT = Path(r"work\refs")
OUT.mkdir(parents=True, exist_ok=True)

REPOS = {
    "OpenNovel": ("Cppys/OpenNovel", "main"),
    "long-novel-writer": ("jiaw-Zh/long-novel-writer", "main"),
    "aiAIfiction": ("liaoma1993/aiAIfiction", "main"),
}


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2)
    raise last


def tree(repo, branch):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    data = json.loads(fetch(url))
    return [t["path"] for t in data.get("tree", []) if t["type"] == "blob"]


def main():
    for name, (repo, branch) in REPOS.items():
        try:
            paths = tree(repo, branch)
        except Exception as e:  # noqa: BLE001
            print(name, "tree fail", str(e)[:120])
            continue
        target = OUT / name
        target.mkdir(exist_ok=True)
        (target / "_files.txt").write_text("\n".join(paths), encoding="utf-8")
        print(name, "files:", len(paths))
        for p in paths:
            low = p.lower()
            if any(
                k in low
                for k in (
                    "readme",
                    "memory",
                    "prompt",
                    "outline",
                    "planner",
                    "writer",
                    "world",
                    "character",
                    "continuity",
                    "review",
                    "skill.md",
                    "chapter",
                    "state",
                )
            ):
                try:
                    data = fetch(f"https://raw.githubusercontent.com/{repo}/{branch}/{p}")
                    fp = target / p.replace("/", "__")
                    fp.write_bytes(data)
                except Exception as e:  # noqa: BLE001
                    print("  skip", p, str(e)[:80])


if __name__ == "__main__":
    main()
