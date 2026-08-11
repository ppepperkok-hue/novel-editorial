"""pytest collection hygiene: ignore vendored/archived/build directories.

These directories are git-ignored third-party code, archived copies, or
build outputs; their tests must not break project-wide collection.
"""

collect_ignore = [
    "n8n_tmp",
    "docs/research/skills",
    "desktop/release",
    "exports/archive",
    "tools/archive",
]
