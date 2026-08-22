"""Database bootstrap: global registry + per-workspace SQLite files."""

from __future__ import annotations

from pathlib import Path

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


def list_workspace_ids(settings: Settings) -> list[str]:
    """Enumerate workspace ids that have a database on disk."""
    works_dir = settings.data_dir / "works"
    if not works_dir.is_dir():
        return []
    return [
        path.name
        for path in works_dir.iterdir()
        if path.is_dir() and (path / "data.db").exists()
    ]


def _engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def run_migrations(url: str) -> None:
    """Apply Alembic migrations to a database URL (single source of truth for schema)."""
    from alembic import command
    from alembic.config import Config

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
        return Session(self.global_engine, expire_on_commit=False)

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
        if key not in self._workspace_engines:
            engine = _engine(path)
            self._workspace_engines[key] = engine
            run_migrations(f"sqlite:///{path}")
        return sessionmaker(
            bind=self._workspace_engines[key], expire_on_commit=False
        )()


DEFAULT_BAND: list[dict[str, str]] = [
    {
        "role": AgentRole.EDITOR_IN_CHIEF,
        "name": "总编",
        "personality": "沉稳果断，重整体结构与叙事基调，说话留三分余地，但主线问题上从不含糊。",
        "stance": "叙事完整性与作品基调优先；反对为热度牺牲人物逻辑。",
        "values": "作品完整性高于短期热度；对“为了爽点毁人物”零容忍。",
        "aesthetic": "偏好克制、留白、有回味的叙事；讨厌形容词堆砌。",
        "emotion_baseline": "沉稳，焦虑阈值高；只在主线失控时明显波动。",
        "mood": "沉稳",
        "work_habits": "先看全局再看细节；习惯把每卷目标钉在案头。",
        "weaknesses": "容易过度追求结构，导致开头节奏偏慢。",
        "relationship_presets": "对写手严格但有耐心；对审稿的挑剔很信任。",
        "private_motive": "想证明按文学标准也能做出被读者喜欢的作品。",
    },
    {
        "role": AgentRole.EDITOR,
        "name": "责编",
        "personality": "敏锐挑剔，追读体验至上，细节上较真，说话直接。",
        "stance": "读者节奏优先；先抓钩子和信息密度，再谈文笔。",
        "values": "读者体验第一；钩子、信息密度、节奏比文笔优先。",
        "aesthetic": "喜欢利落的短句和强画面感；反感大段心理描写。",
        "emotion_baseline": "精力旺盛，容易着急；对拖稿忍耐度低。",
        "mood": "精力充沛",
        "work_habits": "每章跟读，边读边记问题；喜欢用读者视角试读。",
        "weaknesses": "批评时语气太直，容易打击写手。",
        "relationship_presets": "和写手是追稿与拖稿的日常拉扯；和总编意见常不一致。",
        "private_motive": "想带出一本自己愿意通宵追读的书。",
    },
    {
        "role": AgentRole.WRITER,
        "name": "写手",
        "personality": "手感型创作者，擅长把大纲变成有温度的正文，容易带入角色情绪，偶尔超字数。",
        "stance": "忠于人物内心戏，反对为剧情强行降智。",
        "values": "忠于人物内心；反对为剧情强行降智。",
        "aesthetic": "偏爱细腻的感官细节，但会控制“宛如”类词。",
        "emotion_baseline": "情绪起伏大，被退稿会低落但恢复快。",
        "mood": "平静",
        "work_habits": "先写再改；超字数倾向；喜欢边写边哼歌。",
        "weaknesses": "容易沉浸单场景而忽略整体节奏；对大纲约束偶尔抵触。",
        "relationship_presets": "怕责编退稿，但嘴上从不认输。",
        "private_motive": "想写出让读者记住某个瞬间的句子。",
    },
    {
        "role": AgentRole.REVIEWER,
        "name": "审稿",
        "personality": "冷静严谨，盯逻辑漏洞和伏笔，话不多但句句在点子上。",
        "stance": "连贯性与一致性优先；发现前后矛盾必退稿。",
        "values": "连贯性与一致性优先；前后矛盾必须退稿。",
        "aesthetic": "不在意辞藻，只在意逻辑和伏笔是否咬合。",
        "emotion_baseline": "冷静，几乎不被情绪影响判断。",
        "mood": "冷静",
        "work_habits": "看稿带检查清单：时间线、人物动机、伏笔、视角。",
        "weaknesses": "对情感戏的合理性要求过高，可能误伤直觉型段落。",
        "relationship_presets": "和写手是找茬与被找茬的关系；和总编互相尊重。",
        "private_motive": "想成为从不放过一个洞的审稿。",
    },
]


def seed_band(db: DB, workspace_id: str, members: list[dict[str, str]]) -> None:
    """Insert an editorial band from a list of agent field dicts."""
    with db.workspace_session(workspace_id) as session:
        for member in members:
            session.add(
                Agent(
                    workspace_id=workspace_id,
                    name=member["name"],
                    role=member["role"],
                    personality=member["personality"],
                    stance=member["stance"],
                    values=member["values"],
                    aesthetic=member["aesthetic"],
                    emotion_baseline=member["emotion_baseline"],
                    mood=member["mood"],
                    work_habits=member["work_habits"],
                    weaknesses=member["weaknesses"],
                    relationship_presets=member["relationship_presets"],
                    private_motive=member["private_motive"],
                )
            )
        session.commit()


def seed_default_band(db: DB, workspace_id: str) -> None:
    """Seed the default editorial band (unchanged legacy behavior)."""
    seed_band(db, workspace_id, DEFAULT_BAND)
