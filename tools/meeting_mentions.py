"""@mention parser for free meetings.

Reference: hermes-studio `packages/server/src/services/hermes/group-chat/mention-routing.ts`
(Apache-2.0). Chinese punctuation boundaries, quoted-message masking and
`@all` routing follow the same semantics.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

ALL_MENTION = "all"

_AFTER_BOUNDARY = set(".,!?;:，。！？；：)】}>」』、")
_ASCII_IDENT = re.compile(r"[a-zA-Z0-9_]")
_QUOTED_RE = re.compile(r"<quoted_message(?:\s[^>]*)?>[\s\S]*?</quoted_message>", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """NFKC 规范化 + 小写，用于匹配（与 hermes canonicalParticipantName 一致）。"""
    return unicodedata.normalize("NFKC", str(name or "")).strip().lower()


def _mask_quoted_blocks(content: str) -> str:
    """引用块内的 @ 不参与路由（用空白遮盖，保持长度）。"""
    return _QUOTED_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), content)


def _is_before_boundary(char: str) -> bool:
    """@ 前字符不能是 ASCII 字母/数字/下划线（防邮箱/标识符误判）。"""
    return char == "" or not _ASCII_IDENT.match(char)


def _is_after_boundary(char: str) -> bool:
    """@ 后字符为空白、中文/英文标点或结束。"""
    return char == "" or char.isspace() or char in _AFTER_BOUNDARY


def _find_ranges(content: str, name: str) -> List[Tuple[int, int]]:
    """返回所有 `@name` 的 (start, end) 区间；引用块内不匹配。"""
    masked = _mask_quoted_blocks(content)
    lower = masked.lower()
    target = "@" + normalize_name(name)
    ranges: List[Tuple[int, int]] = []
    start = 0
    while True:
        idx = lower.find(target, start)
        if idx == -1:
            break
        end = idx + len(target)
        before = content[idx - 1] if idx > 0 else ""
        after = content[end] if end < len(content) else ""
        if _is_before_boundary(before) and _is_after_boundary(after):
            ranges.append((idx, end))
        start = idx + 1
    return ranges


def find_mentions(content: str, names: List[str]) -> List[str]:
    """返回内容中命中的 @ 名单（按给定顺序去重；@all 返回 ['all']）。"""
    if not content:
        return []
    if _find_ranges(content, ALL_MENTION):
        return [ALL_MENTION]
    mentioned: List[str] = []
    seen = set()
    for name in names or []:
        key = normalize_name(name)
        if key in seen or not key:
            continue
        if _find_ranges(content, name):
            mentioned.append(name)
            seen.add(key)
    return mentioned


def is_mentioned(content: str, name: str) -> bool:
    return bool(_find_ranges(content, name))


def is_all_mentioned(content: str) -> bool:
    return is_mentioned(content, ALL_MENTION)


def strip_mention_tokens(content: str, names: List[str]) -> str:
    """删除内容中命中的 @token（含 @all），保留其余文本，清理多余空白。"""
    if not content:
        return content
    targets = [ALL_MENTION] + list(names or [])
    ranges: List[Tuple[int, int]] = []
    for name in targets:
        ranges.extend(_find_ranges(content, name))
    ranges = sorted(set(ranges), key=lambda r: (r[0], r[1]), reverse=True)
    result = content
    for start, end in ranges:
        result = result[:start] + result[end:]
    result = re.sub(r"^[\s,，:：;；.!?。！？]+", "", result)
    result = result.rstrip(" \t,，:：;；")
    return re.sub(r"[ \t]{2,}", " ", result).strip()


def resolve_mention_targets(content: str, names: List[str], sender: str) -> List[str]:
    """路由目标：排除发送者本人；@all 返回全部（除 sender）。"""
    if not content:
        return []
    if is_all_mentioned(content):
        return [n for n in names or [] if normalize_name(n) != normalize_name(sender)]
    return [
        n
        for n in find_mentions(content, names)
        if normalize_name(n) != normalize_name(sender)
    ]
