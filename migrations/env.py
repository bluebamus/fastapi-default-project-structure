from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import Base and every domain app's models so that autogenerate discovers
# ALL domain tables. 새 앱 추가 시 이 import 목록에 한 줄 추가한다.
# ---------------------------------------------------------------------------
import app.domains.blog.models.models  # noqa: E402,F401
import app.domains.home.models.models  # noqa: E402,F401
import app.domains.reply.models.models  # noqa: E402,F401
import app.domains.sns.models.models  # noqa: E402,F401
import app.domains.user.models.models  # noqa: E402,F401
from app.core.db.session import Base  # noqa: E402
from config import db_settings  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Resolve the database URL.
# 환경변수를 직접 읽지 않는다 — 설정은 config.py 가 단독으로 로드한다.
# db_settings.ALEMBIC_URL 이 ALEMBIC_DATABASE_URL 오버라이드(로컬/CI 의 SQLite 등)와
# primary DSN 의 동기 드라이버 치환(aiomysql → pymysql)을 모두 처리한다.
# ---------------------------------------------------------------------------
config.set_main_option("sqlalchemy.url", db_settings.ALEMBIC_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
