"""Summarize parallel slice review reports into one merged report.

After `run_review.ps1 -Scope slices` finishes, this tool reads every
`*-slice-*.md` report, extracts P0-P3 findings (bullet and table formats),
and writes a single `*-slices-summary.md` next to them.

Usage:
    python tools/summarize_slices.py --dir docs/reviews --stamp 20260812-0045
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_LEVEL_RE = re.compile(r"\[P([0-3])\]|\|\s*P([0-3])\s*\|")


def _extract_findings(text):
    findings = {0: [], 1: [], 2: [], 3: []}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("### [P"):
            continue  # heading rows duplicate the entry/table rows below
        m = _LEVEL_RE.search(line)
        if not m:
            continue
        level = int(m.group(1) or m.group(2))
        clean = re.sub(r"^[-*|]\s*", "", line)
        clean = re.sub(r"`", "", clean)
        clean = re.sub(r"\s+", " ", clean)
        findings[level].append(clean[:220])
    return findings


def summarize(directory, stamp):
    d = Path(directory)
    slices = sorted(d.glob(f"{stamp}-slice-*.md"))
    if not slices:
        return {"ok": False, "error": f"no slice reports for {stamp}"}
    lines = [f"# 分片审查汇总 · {stamp}", ""]
    totals = {0: 0, 1: 0, 2: 0, 3: 0}
    for path in slices:
        name = path.name.replace(f"{stamp}-slice-", "").replace(".md", "")
        findings = _extract_findings(path.read_text(encoding="utf-8"))
        lines.append(f"## {name}")
        lines.append("")
        any_found = False
        for level in (0, 1, 2, 3):
            items = findings[level]
            if not items:
                continue
            any_found = True
            totals[level] += len(items)
            lines.append(f"### P{level}（{len(items)}）")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")
        if not any_found:
            lines.append("（本分片无显式 P0-P3 条目）")
            lines.append("")
    lines.append("## 统计")
    lines.append("")
    lines.append("| 级别 | 数量 |")
    lines.append("| --- | --- |")
    for level in (0, 1, 2, 3):
        lines.append(f"| P{level} | {totals[level]} |")
    out = d / f"{stamp}-slices-summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "out": str(out), "totals": totals, "slices": len(slices)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="merge slice review reports")
    ap.add_argument("--dir", default=str(ROOT / "docs" / "reviews"))
    ap.add_argument("--stamp", required=True)
    args = ap.parse_args()
    print(__import__("json").dumps(summarize(args.dir, args.stamp), ensure_ascii=False))


if __name__ == "__main__":
    main()
