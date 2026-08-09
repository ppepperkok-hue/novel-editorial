"""Robust paragraph splitting for web-novel text."""

import re

CUTS = set("。！？；")
QUOTES = set("”’」』")


def _split_long(text):
    out = []
    buf = ""
    i = 0
    while i < len(text):
        ch = text[i]
        buf += ch
        if len(buf) >= 80 and ch in CUTS:
            if i + 1 < len(text) and text[i + 1] in QUOTES:
                buf += text[i + 1]
                i += 1
            out.append(buf.strip())
            buf = ""
        i += 1
    if buf.strip():
        out.append(buf.strip())
    return [p for p in out if p]


def split_paragraphs(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) <= 1:
        paras = _split_long(paras[0] if paras else text)
    return paras


def to_html(text):
    paras = split_paragraphs(text)
    return "".join(f"<p>{p}</p>" for p in paras)
