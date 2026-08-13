"""Database bootstrap: global registry + per-workspace SQLite files."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from novel_editorial.core.config import Settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.models import Agent, AgentRole

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"


def global_db_path(settings: Settings) -> Path:
    return settings.data_dir / "global.db"


def workspace_db_path(settings: Settings, workspace_id: str) -> Path:
    return settings.data_dir / "works" / workspace_id / "data.db"


def _engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def run_migrations(url: str) -> None:
    """Apply Alembic migrations to a database URL (single source of truth for schema)."""
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


class DB:
    """Owns the global engine and lazily opens per-workspace engines."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.global_engine = _engine(global_db_path(settings))
        self._workspace_engines: dict[str, Engine] = {}

    def init_schema(self) -> None:
        run_migrations(f"sqlite:///{global_db_path(self.settings)}")

    def ping(self) -> None:
        with self.global_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def global_session(self) -> Session:
        return Session(self.global_engine)

    def create_workspace_db(self, workspace_id: str) -> None:
        path = workspace_db_path(self.settings, workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = _engine(path)
        self._workspace_engines[str(path)] = engine
        run_migrations(f"sqlite:///{path}")

    def workspace_session(self, workspace_id: str) -> Session:
        path = workspace_db_path(self.settings, workspace_id)
        if not path.exists():
            raise NovelError(ErrorCode.NOT_FOUND, f"workspace not found: {workspace_id}")
        key = str(path)
        engine = self._workspace_engines.get(key)
        if engine is None:
            engine = _engine(path)
            self._workspace_engines[key] = engine
        return sessionmaker(bind=engine)()


DEFAULT_BAND: list[dict[str, str]] = [
    {
        "role": AgentRole.EDITOR_IN_CHIEF,
        "name": "总编",
        "personality": "沉稳果断，重整体结构与叙事基调，说话留三分余地，但主线问题上从不含糊。",
        "stance": "叙事完整性与作品基调优先；反对为热度牺牲人物逻辑。",
    },
    {
        "role": AgentRole.EDITOR,
        "name": "责编",
        "personality": "敏锐挑剔，追读体验至上，细节上较真，说话直接。",
        "stance": "读者节奏优先；先抓钩子和信息密度，再谈文笔。",
    },
    {
        "role": AgentRole.WRITER,
        "name": "写手",
        "personality": "手感型创作者，擅长把大纲变成有温度的正文，容易带入角色情绪，偶尔超字数。",
        "stance": "忠于人物内心戏，反对为剧情强行降智。",
    },
    {
        "role": AgentRole.REVIEWER,
        "name": "审稿",
        "personality": "冷静严谨，盯逻辑漏洞和伏笔，话不多但句句在点子上。",
        "stance": "连贯性与一致性优先；发现前后矛盾必退稿。",
    },
]


def seed_default_band(db: DB, workspace_id: str) -> None:
    with db.workspace_session(workspace_id) as session:
        for member in DEFAULT_BAND:
            session.add(
                Agent(
                    workspace_id=workspace_id,
                    name=member["name"],
                    role=member["role"],
                    personality=member["personality"],
                    stance=member["stance"],
                )
            )
        session.commit()
