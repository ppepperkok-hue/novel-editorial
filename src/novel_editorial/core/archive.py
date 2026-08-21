"""Workspace archive export/import (N25 S1).

Export takes a consistent sqlite3 backup snapshot of one workspace's data.db,
packages it with a verifiable manifest into a ZIP, and writes the archive
atomically. Import validates the archive, restores the workspace under a fresh
id, migrates the copied database to schema head, registers it in the global
registry, and records one SYSTEM ``workspace_imported`` event.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from novel_editorial.core.chat import get_workspace_or_raise
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.events import EventType
from novel_editorial.store.db import DB, run_migrations, workspace_db_path
from novel_editorial.store.events import record_event
from novel_editorial.store.models import Workspace

ARCHIVE_FORMAT = "novel-editorial-workspace"
ARCHIVE_VERSION = 1

_REQUIRED_WORKSPACE_KEYS = ("id", "title", "genre", "description", "status", "created_at")
_CHUNK_SIZE = 1024 * 1024


def _sha256(path: Path) -> str:
    """Return the hex sha256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_export_target(target: Path, workspace_id: str) -> Path:
    """Resolve the final archive path from the caller's target semantics."""
    if target.exists():
        if not target.is_dir():
            raise NovelError(ErrorCode.USAGE_ERROR, f"export target exists: {target}")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        final_path = target / f"novel-export-{workspace_id}-{stamp}.zip"
    else:
        if not target.parent.exists():
            raise NovelError(
                ErrorCode.USAGE_ERROR,
                f"export target directory not found: {target.parent}",
            )
        final_path = target
    if final_path.exists():
        raise NovelError(ErrorCode.USAGE_ERROR, f"export target exists: {final_path}")
    return final_path


def export_workspace_archive(db: DB, workspace_id: str, target: str | Path) -> Path:
    """Export one workspace to a verifiable ZIP archive; never modifies source data."""
    workspace = get_workspace_or_raise(db, workspace_id)
    final_path = _resolve_export_target(Path(target), workspace.id)
    source_db = workspace_db_path(db.settings, workspace_id)
    if not source_db.exists():
        raise NovelError(ErrorCode.NOT_FOUND, f"workspace database not found: {workspace_id}")

    with tempfile.TemporaryDirectory(prefix="novel-export-") as tmp_dir:
        snapshot = Path(tmp_dir) / "data.db"
        uri = f"file:///{source_db.resolve().as_posix()}?mode=ro"
        # sqlite3 connection context managers only manage transactions, not
        # close: close both handles explicitly so the snapshot can be removed.
        source_conn = sqlite3.connect(uri, uri=True)
        snapshot_conn = sqlite3.connect(snapshot)
        try:
            source_conn.backup(snapshot_conn)
        finally:
            snapshot_conn.close()
            source_conn.close()
        manifest = {
            "format": ARCHIVE_FORMAT,
            "version": ARCHIVE_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "workspace": {
                "id": workspace.id,
                "title": workspace.title,
                "genre": workspace.genre,
                "description": workspace.description,
                "status": workspace.status,
                "created_at": workspace.created_at.isoformat(),
            },
            "files": {"data.db": _sha256(snapshot)},
        }

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{final_path.name}.", suffix=".tmp", dir=final_path.parent
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as raw:
                with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(snapshot, arcname="data.db")
                    archive.writestr(
                        "manifest.json",
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    )
                raw.flush()
                os.fsync(raw.fileno())
            os.replace(tmp_path, final_path)
        finally:
            tmp_path.unlink(missing_ok=True)
    return final_path


def _extract_archive(archive: Path, dest: Path) -> None:
    """Extract every member into ``dest``, rejecting any path escape."""
    dest_root = dest.resolve()
    try:
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                target = (dest / member.filename).resolve()
                if not target.is_relative_to(dest_root):
                    raise NovelError(
                        ErrorCode.USAGE_ERROR,
                        f"invalid archive: unsafe path {member.filename!r}",
                    )
                if member.is_dir():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
    except NovelError:
        raise
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
        raise NovelError(ErrorCode.USAGE_ERROR, f"invalid archive: {exc}") from exc


def _load_manifest(tmp_dir: Path) -> dict:
    manifest_path = tmp_dir / "manifest.json"
    if not manifest_path.is_file():
        raise NovelError(ErrorCode.USAGE_ERROR, "invalid archive: missing manifest.json")
    try:
        with manifest_path.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NovelError(
            ErrorCode.USAGE_ERROR, "invalid archive: manifest.json is not valid JSON"
        ) from exc
    if not isinstance(manifest, dict):
        raise NovelError(ErrorCode.USAGE_ERROR, "invalid archive: manifest must be an object")
    return manifest


def _validate_manifest(manifest: dict) -> None:
    if manifest.get("format") != ARCHIVE_FORMAT:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid archive: unsupported format {manifest.get('format')!r}",
        )
    if manifest.get("version") != ARCHIVE_VERSION:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            f"invalid archive: unsupported version {manifest.get('version')!r}",
        )
    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict) or any(
        key not in workspace for key in _REQUIRED_WORKSPACE_KEYS
    ):
        raise NovelError(
            ErrorCode.USAGE_ERROR, "invalid archive: manifest.workspace incomplete"
        )
    files = manifest.get("files")
    if (
        not isinstance(files, dict)
        or not isinstance(files.get("data.db"), str)
        or not files["data.db"]
    ):
        raise NovelError(
            ErrorCode.USAGE_ERROR, "invalid archive: manifest.files.data.db missing"
        )


def _parse_manifest_datetime(value: object) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise NovelError(
            ErrorCode.USAGE_ERROR,
            "invalid archive: manifest.workspace.created_at is invalid",
        ) from exc


def _register_workspace(db: DB, workspace_id: str, info: dict) -> Workspace:
    workspace = Workspace(
        id=workspace_id,
        title=info["title"],
        genre=info["genre"],
        description=info["description"],
        status=info["status"],
        created_at=_parse_manifest_datetime(info["created_at"]),
    )
    with db.global_session() as session:
        session.add(workspace)
        session.commit()
    return workspace


def _rewrite_workspace_id(path: Path, old_id: str, new_id: str) -> None:
    """Point every copied row with a workspace_id column at the new workspace id."""
    conn = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        for table in tables:
            columns = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            if "workspace_id" not in columns:
                continue
            quoted = table.replace('"', '""')
            conn.execute(
                f'UPDATE "{quoted}" SET workspace_id = ? WHERE workspace_id = ?',
                (new_id, old_id),
            )
        conn.commit()
    finally:
        conn.close()


def _cleanup_import_artifacts(db: DB, workspace_id: str) -> None:
    """Best-effort removal of a half-finished imported workspace."""
    path = workspace_db_path(db.settings, workspace_id)
    engine = db._workspace_engines.pop(str(path), None)
    if engine is not None:
        engine.dispose()
    try:
        with db.global_session() as session:
            session.query(Workspace).filter(Workspace.id == workspace_id).delete(
                synchronize_session=False
            )
            session.commit()
    except Exception as exc:  # cleanup must never mask the original failure
        print(f"warning: import cleanup failed: {exc}", file=sys.stderr)
    shutil.rmtree(path.parent, ignore_errors=True)


def import_workspace_archive(db: DB, archive_path: str | Path) -> Workspace:
    """Import one archive as a brand-new workspace; never overwrites existing data."""
    archive = Path(archive_path)
    if not archive.exists():
        raise NovelError(ErrorCode.NOT_FOUND, f"archive not found: {archive}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="novel-import-"))
    try:
        _extract_archive(archive, tmp_dir)
        manifest = _load_manifest(tmp_dir)
        _validate_manifest(manifest)
        data_db = tmp_dir / "data.db"
        if not data_db.is_file():
            raise NovelError(ErrorCode.USAGE_ERROR, "invalid archive: missing data.db")
        expected = manifest["files"]["data.db"]
        if _sha256(data_db) != expected:
            raise NovelError(ErrorCode.USAGE_ERROR, "invalid archive: data.db sha256 mismatch")
        workspace_info = manifest["workspace"]

        new_id = uuid.uuid4().hex
        new_db = workspace_db_path(db.settings, new_id)
        new_db.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(data_db, new_db)
            run_migrations(f"sqlite:///{new_db}")
            _rewrite_workspace_id(new_db, workspace_info["id"], new_id)
            workspace = _register_workspace(db, new_id, workspace_info)
            record_event(
                db,
                new_id,
                type=EventType.SYSTEM,
                actor="system",
                payload={"kind": "workspace_imported", "source_id": workspace_info["id"]},
            )
        except Exception:
            _cleanup_import_artifacts(db, new_id)
            raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return workspace
