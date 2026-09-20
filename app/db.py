from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from pathlib import Path
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root / "alembic.ini"))
    config.set_main_option("script_location",str(root / "alembic"))
    tables=inspect(engine).get_table_names()
    if "interactions" in tables and "alembic_version" not in tables:
        columns={c["name"] for c in inspect(engine).get_columns("interactions")}
        boundary_columns={c["name"] for c in inspect(engine).get_columns("forget_boundaries")} if "forget_boundaries" in tables else set()
        revision=("head" if {"subject_entity_id","value_entity_id"} <= boundary_columns else "0002_v2_foundation") if "processing_status" in columns else "0001_initial"
        command.stamp(config,revision)
    command.upgrade(config,"head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
