from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
#
# disable_existing_loggers=False 가 핵심이다. fileConfig 의 기본값(True)은 이미
# 만들어진 로거를 **전부 비활성화**한다. alembic 을 애플리케이션과 같은 프로세스에서
# 돌리면(기동 시 마이그레이션, 테스트 하네스 등) 그 순간 앱 로깅이 조용히 죽는다.
# 증상은 "어느 순간부터 로그가 안 나온다"로 나타나 원인을 찾기 어렵다.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# ---------------------------------------------------------------------------
# Import Base and every domain app's models so that autogenerate discovers
# ALL domain tables. 목록은 models_registry 가 디렉터리에서 판별하므로
# 새 앱을 추가해도 이 파일은 손대지 않는다.
# ---------------------------------------------------------------------------
from app.core.db.models_registry import import_all_models  # noqa: E402
from app.core.db.session import Base  # noqa: E402
from config import db_settings  # noqa: E402

import_all_models()

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
