from logging.config import fileConfig

import sqlite_vec  # type: ignore[import-untyped]
from alembic import context
from mnemos.config import settings
from mnemos.models import Memory, MemoryTag, OAuthClient, SchemaVersion, Tag  # noqa: F401
from mnemos.models.base import Base
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings.db_path.parent.mkdir(parents=True, exist_ok=True)

target_metadata = Base.metadata

_VIRTUAL_TABLE_PREFIXES = ("memories_fts", "memories_vec")


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    if type_ == "table" and any(name.startswith(p) for p in _VIRTUAL_TABLE_PREFIXES):
        return False
    return True


def _make_engine():
    engine = create_engine(f"sqlite:///{settings.db_path}")

    @event.listens_for(engine, "connect")
    def load_vec(dbapi_conn, _):  # noqa: ANN001
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)

    return engine


def run_migrations_offline() -> None:
    context.configure(
        url=f"sqlite:///{settings.db_path}",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = _make_engine()
    with engine.connect() as connection:
        do_run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
