"""Configuration loading: env vars + optional TOML overrides."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from novel_editorial.core.errors import ErrorCode, NovelError

_TRUE_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_ENABLED_VALUES = frozenset({"0", "false", "no", "off"})


def _parse_enabled(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in _TRUE_ENABLED_VALUES:
        return True
    if lowered in _FALSE_ENABLED_VALUES:
        return False
    raise NovelError(ErrorCode.CONFIG_ERROR, f"invalid proactive enabled: {value!r}")


def _load_int_setting(
    env: Mapping[str, str],
    defaults: dict,
    *,
    env_key: str,
    toml_key: str,
    fallback: int,
    label: str,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Read one integer setting: TOML default first, then env override."""
    default_value = defaults.get(toml_key, fallback)
    raw_value = env.get(env_key, str(default_value))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid {label}: {raw_value!r}",
        ) from exc
    if value < 0 or (min_value is not None and value < min_value) or (
        max_value is not None and value > max_value
    ):
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid {label}: {raw_value!r}",
        )
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    config_path: Path
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    log_level: str = "INFO"
    quality_threshold: int = 8
    memory_decay_per_day: int = 5
    memory_rehearsal_boost: int = 25
    memory_archive_threshold: int = 20
    proactive_enabled: bool = True
    proactive_max_per_agent: int = 3
    embedding_backend: str = "local"
    embedding_model: str = ""
    embedding_dim: int = 256
    embedding_top_k: int = 5
    defaults: dict = field(default_factory=dict)


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = env if env is not None else os.environ
    data_dir = Path(env.get("NOVEL_DATA_DIR", "./data"))
    config_path = Path(env.get("NOVEL_CONFIG", "./config.toml"))
    config = _read_toml(config_path)
    defaults = config.get("defaults", {})
    default_threshold = defaults.get("quality_threshold", 8)
    threshold_value = env.get("NOVEL_QUALITY_THRESHOLD", str(default_threshold))
    try:
        quality_threshold = int(threshold_value)
    except (TypeError, ValueError) as exc:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid quality threshold: {threshold_value!r}",
        ) from exc
    default_proactive_enabled = defaults.get("proactive_enabled", True)
    enabled_value = env.get("NOVEL_PROACTIVE_ENABLED", str(default_proactive_enabled))
    proactive_enabled = _parse_enabled(enabled_value)
    default_proactive_max = defaults.get("proactive_max_per_agent", 3)
    max_value = env.get("NOVEL_PROACTIVE_MAX_PER_AGENT", str(default_proactive_max))
    try:
        proactive_max_per_agent = int(max_value)
    except (TypeError, ValueError) as exc:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid proactive max per agent: {max_value!r}",
        ) from exc
    if proactive_max_per_agent < 0:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid proactive max per agent: {max_value!r}",
        )
    memory_decay_per_day = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_MEMORY_DECAY_PER_DAY",
        toml_key="memory_decay_per_day",
        fallback=5,
        label="memory decay per day",
    )
    memory_rehearsal_boost = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_MEMORY_REHEARSAL_BOOST",
        toml_key="memory_rehearsal_boost",
        fallback=25,
        label="memory rehearsal boost",
    )
    memory_archive_threshold = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_MEMORY_ARCHIVE_THRESHOLD",
        toml_key="memory_archive_threshold",
        fallback=20,
        label="memory archive threshold",
        max_value=100,
    )
    embedding_backend = env.get(
        "NOVEL_EMBEDDING_BACKEND", defaults.get("embedding_backend", "local")
    )
    if embedding_backend not in ("local", "api"):
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid embedding backend: {embedding_backend!r} "
            "(expected one of: local, api)",
        )
    raw_embedding_model = env.get("NOVEL_EMBEDDING_MODEL")
    if raw_embedding_model is None:
        raw_embedding_model = defaults.get("embedding_model", "")
    embedding_model = str(raw_embedding_model)
    embedding_dim = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_EMBEDDING_DIM",
        toml_key="embedding_dim",
        fallback=256,
        label="embedding dim",
        min_value=32,
        max_value=4096,
    )
    embedding_top_k = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_EMBEDDING_TOP_K",
        toml_key="embedding_top_k",
        fallback=5,
        label="embedding top k",
        min_value=1,
        max_value=50,
    )
    return Settings(
        data_dir=data_dir,
        config_path=config_path,
        llm_api_key=env.get("NOVEL_LLM_API_KEY") or None,
        llm_base_url=env.get("NOVEL_LLM_BASE_URL", "https://api.deepseek.com"),
        llm_model=env.get("NOVEL_LLM_MODEL", "deepseek-chat"),
        log_level=env.get("NOVEL_LOG_LEVEL", "INFO"),
        quality_threshold=quality_threshold,
        memory_decay_per_day=memory_decay_per_day,
        memory_rehearsal_boost=memory_rehearsal_boost,
        memory_archive_threshold=memory_archive_threshold,
        proactive_enabled=proactive_enabled,
        proactive_max_per_agent=proactive_max_per_agent,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        embedding_dim=embedding_dim,
        embedding_top_k=embedding_top_k,
        defaults=defaults,
    )


_DEFAULTS_HEADER_RE = re.compile(
    r"^\s*\[\s*(?P<key>defaults|[\"']defaults[\"'])\s*\]\s*(?:#.*)?$"
)
_SECTION_HEADER_RE = re.compile(r"^\s*\[{1,2}[^\[\]]+\]{1,2}\s*(?:#.*)?$")
_QUALITY_THRESHOLD_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<key>quality_threshold|[\"']quality_threshold[\"'])"
    r"\s*=\s*(?P<tail>.*)$"
)


def _line_eol(line: str) -> str:
    """Return the line ending of a single line (empty for the last line)."""
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _detect_eol(lines: list[str]) -> str:
    """Return the first line ending found in the file, defaulting to LF."""
    for line in lines:
        eol = _line_eol(line)
        if eol:
            return eol
    return "\n"


def _strip_eol(line: str) -> str:
    """Return the line content without its line ending."""
    eol = _line_eol(line)
    return line if not eol else line[: -len(eol)]


def _scan_chunk(
    text: str, in_string: str | None, depth: int
) -> tuple[str | None, int, int]:
    """Scan one chunk of TOML source and return (in_string, depth, comment_start).

    `in_string` is None in code, a triple-double-quote delimiter inside a
    multiline basic string, a triple-single-quote inside a multiline literal
    string, and `"`/`'` inside single-line strings; `depth` counts unclosed
    `[`/`{` at the code level. The first `#` met at the code level starts a
    comment and stops the scan; `comment_start` is its index (or -1 when the
    chunk has no comment).
    """
    index = 0
    comment_start = -1
    while index < len(text):
        char = text[index]
        if in_string is None:
            if char == '"':
                if text.startswith('"""', index):
                    in_string = '"""'
                    index += 3
                    continue
                in_string = '"'
                index += 1
                continue
            if char == "'":
                if text.startswith("'''", index):
                    in_string = "'''"
                    index += 3
                    continue
                in_string = "'"
                index += 1
                continue
            if char in "[{":
                depth += 1
            elif char in "]}":
                depth -= 1
            elif char == "#":
                comment_start = index
                break
            index += 1
            continue
        if in_string == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                in_string = None
            index += 1
            continue
        if in_string == "'":
            if char == "'":
                in_string = None
            index += 1
            continue
        if in_string == '"""':
            if char == "\\":
                index += 2
                continue
            if text.startswith('"""', index):
                in_string = None
                index += 3
                continue
            index += 1
            continue
        # in_string == "'''"
        if text.startswith("'''", index):
            in_string = None
            index += 3
            continue
        index += 1
    return in_string, depth, comment_start


def _structure_flags(lines: list[str]) -> list[bool]:
    """Mark lines that start inside a multiline string or an unclosed array.

    Such lines can never be a section header or a key assignment, so they must
    be skipped when scanning for TOML structure (their text belongs to a
    string or value, not to the document structure).
    """
    flags: list[bool] = []
    in_string: str | None = None
    depth = 0
    for line in lines:
        flags.append(in_string is not None or depth > 0)
        in_string, depth, _ = _scan_chunk(_strip_eol(line), in_string, depth)
    return flags


def _tail_comment(tail: str) -> str:
    """Return the trailing comment (with leading whitespace) of a value tail.

    The first `#` outside strings and nested values starts the comment, so both
    `8  # keep` and `8#keep` keep their comments on a rewrite.
    """
    _, _, comment_start = _scan_chunk(tail, None, 0)
    if comment_start == -1:
        return ""
    value_end = len(tail[:comment_start].rstrip())
    return tail[value_end:]


def set_quality_threshold(config_path: Path, value: int) -> None:
    """Write quality_threshold under [defaults], preserving all other content.

    Creates the file when missing, appends a [defaults] section when absent,
    inserts the key into an existing section when missing, and otherwise
    replaces only the value of the key in place (keeping inline comments and
    every other key/section untouched). Lines inside multiline basic strings
    (\"\"\" or ''') and multiline arrays are never mistaken for structure, so
    string content is not tampered with. The existing file is validated with
    tomllib before any write; invalid TOML raises NovelError(CONFIG_ERROR)
    with the path in the message and context. Repeated calls with the same
    value leave the file byte-for-byte unchanged (idempotent).
    """
    path = Path(config_path)
    rendered = f"quality_threshold = {value}"
    if not path.exists():
        path.write_text(f"[defaults]\n{rendered}\n", encoding="utf-8")
        return

    raw = path.read_text(encoding="utf-8")
    try:
        parsed = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid config file: {path}: {exc}",
            context={"path": str(path)},
        ) from exc

    if not raw:
        path.write_text(f"[defaults]\n{rendered}\n", encoding="utf-8")
        return

    defaults_table = parsed.get("defaults", {})
    current = (
        defaults_table.get("quality_threshold")
        if isinstance(defaults_table, dict)
        else None
    )
    if type(current) is int and current == value:
        return

    lines = raw.splitlines(keepends=True)
    eol = _detect_eol(lines)
    inside = _structure_flags(lines)

    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if not inside[index] and _DEFAULTS_HEADER_RE.match(line)
        ),
        None,
    )
    if header_index is None:
        suffix = f"[defaults]{eol}{rendered}{eol}"
        new_text = raw + suffix if raw.endswith("\n") else raw + eol + suffix
        path.write_text(new_text, encoding="utf-8")
        return

    section_end = len(lines)
    for index in range(header_index + 1, len(lines)):
        if not inside[index] and _SECTION_HEADER_RE.match(lines[index]):
            section_end = index
            break

    for index in range(header_index + 1, section_end):
        if inside[index]:
            continue
        line = lines[index]
        body = _strip_eol(line)
        match = _QUALITY_THRESHOLD_RE.match(body)
        if match is None:
            continue
        indent = match.group("indent")
        key = match.group("key")
        tail = match.group("tail")
        state_after, depth_after, _ = _scan_chunk(tail, None, 0)
        if state_after is None and depth_after == 0:
            lines[index] = (
                f"{indent}{key} = {value}{_tail_comment(tail)}{_line_eol(line)}"
            )
            path.write_text("".join(lines), encoding="utf-8")
            return

        # The value spans several lines (e.g. a multiline string or array);
        # replace the whole construct so the file stays valid TOML.
        state, depth = state_after, depth_after
        comment = ""
        close_eol = eol
        close_index = index
        while close_index + 1 < len(lines):
            close_index += 1
            close_body = _strip_eol(lines[close_index])
            state, depth, comment_start = _scan_chunk(close_body, state, depth)
            if state is None and depth == 0:
                if comment_start != -1:
                    value_end = len(close_body[:comment_start].rstrip())
                    comment = close_body[value_end:]
                close_eol = _line_eol(lines[close_index]) or eol
                break
        lines[index : close_index + 1] = [
            f"{indent}{key} = {value}{comment}{close_eol}"
        ]
        path.write_text("".join(lines), encoding="utf-8")
        return

    if _line_eol(lines[header_index]):
        lines.insert(header_index + 1, f"{rendered}{eol}")
    else:
        lines[header_index] = lines[header_index] + eol
        lines.insert(header_index + 1, f"{rendered}{eol}")
    path.write_text("".join(lines), encoding="utf-8")
