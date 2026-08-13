"""
데이터베이스 세션 및 엔진 관리 모듈

SQLAlchemy 비동기 엔진과 세션 팩토리를 설정합니다.

주요 구성요소:
    - engine: FastAPI 요청 처리용 메인 엔진 = primary(writer) (pool_size=20, max_overflow=20)
    - read_engines: replica(reader) 엔진 목록 (복제 활성 시에만 생성)
    - db_router: 읽기/쓰기 바인딩을 결정하는 DatabaseRouter
    - background_engine: 백그라운드 태스크용 분리 엔진 (pool_size=10, max_overflow=10)
    - AsyncSessionLocal: 메인 세션 팩토리
    - BackgroundSessionLocal: 백그라운드 세션 팩토리

DB 세션 Dependency (정식 이름 — TX-005):
    - get_read_only_db_session():  GET/HEAD 및 변경 없는 조회 (쓰기 시도 시 실패)
    - get_writer_db_session():     쓰기·조회 후 쓰기 (첫 쿼리부터 primary 고정)
    - get_routed_db_session():     승인된 특수 경로의 동적 라우팅
    - get_background_db_session(): background 전용 pool
    - background_db_session():     요청 밖 context manager (Celery 등)

    이름에 ``db_session`` 을 넣는 이유는 사용자 세션·HTTP 세션과 구분하기 위해서다.
    옛 이름(get_session/get_read_session/get_write_session/get_background_session/
    background_session)은 전환 기간의 deprecated 별칭이며 신규 코드에서 쓰지 않는다.

커넥션 풀 분리 이유:
    백그라운드 태스크(예: 접속 로그 저장)가 메인 API 요청의 커넥션 풀을
    고갈시키지 않도록 별도의 풀을 사용합니다.

읽기/쓰기 분리:
    DB_ROUTER_ENABLED=true 면 세션이 구문 성격에 따라 엔진을 자동 선택합니다.
    DB_REPLICATION_ENABLED=true 를 함께 켜면 SELECT 는 replica 로, 쓰기는 primary 로
    나갑니다. 라우터를 끄면 모든 쿼리가 단일 엔진으로 갑니다(기존 동작).
    자세한 규칙은 app/core/db/router.py 를 참고하세요.

사용 예시:
    # 조회 Dependency (기능 dependencies 가 Service 를 조립한다)
    async def get_user_service_readonly(
        db_session: AsyncSession = Depends(get_read_only_db_session),
    ) -> UserService:
        return UserService(db_session)

    # 쓰기 Dependency
    async def get_user_service(
        db_session: AsyncSession = Depends(get_writer_db_session),
    ) -> UserService:
        return UserService(db_session)

    # 요청 밖(백그라운드·Celery)
    async def save_log(data: dict):
        async with background_db_session() as db_session:
            db_session.add(AccessLog(**data))
            await db_session.commit()
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,  # noqa: F401 - re-export
    create_routing_sessionmaker,
    mark_read_only,
    using_writer,
)
from app.core.models.models_base import Base  # noqa: F401 - re-export
from app.utils.logs import get_logger
from config import db_settings

logger = get_logger("database")


# =============================================================================
# 메인 엔진 (FastAPI 요청용) = primary(writer)
# =============================================================================
# API 요청 처리를 위한 커넥션 풀
# - pool_size: 기본 유지 연결 수 (20)
# - max_overflow: 추가 허용 연결 수 (20) → 최대 40개 동시 연결
# - pool_pre_ping: 연결 사용 전 유효성 검사 (죽은 연결 자동 복구)
# - pool_recycle: 연결 재활용 주기 (MySQL wait_timeout보다 짧게 설정)
engine = create_async_engine(
    url=db_settings.MYSQL_WRITER_URL,
    echo=False,  # SQL 로깅 (개발 시 True로 설정)
    pool_size=20,
    max_overflow=20,
    pool_timeout=30,  # 풀에서 연결 대기 시간 (초)
    pool_recycle=280,  # MySQL 기본 wait_timeout(28800s), 클라우드는 보통 300s
    pool_pre_ping=True,
    pool_reset_on_return="rollback",  # 반환 시 롤백으로 세션 초기화
    connect_args={
        "connect_timeout": 10,  # DB 연결 타임아웃 (초)
        "charset": "utf8mb4",  # 이모지 등 4바이트 UTF-8 지원
    },
)

# `engine` 은 SQLAdmin·Alembic 등 기존 소비처가 쓰는 이름이라 유지하고,
# 역할이 드러나는 별칭을 함께 노출한다.
writer_engine = engine


# =============================================================================
# replica 엔진 (읽기 전용) — 복제 활성 시에만 생성
# =============================================================================
def _create_read_engine(url: str) -> AsyncEngine:
    """replica 용 엔진을 만든다.

    읽기는 보통 쓰기보다 트래픽이 많고 트랜잭션이 짧으므로 풀을 primary 와
    같은 크기로 잡되, replica 대수만큼 커넥션이 곱해진다는 점에 유의한다.
    """
    return create_async_engine(
        url=url,
        echo=False,
        pool_size=20,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=280,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
        connect_args={
            "connect_timeout": 10,
            "charset": "utf8mb4",
        },
    )


# 복제가 꺼져 있으면 빈 목록 → 라우터는 읽기도 primary 로 보낸다.
read_engines: list[AsyncEngine] = [
    _create_read_engine(url) for url in db_settings.MYSQL_REPLICA_URLS
]

# 읽기/쓰기 바인딩을 결정하는 라우터 (라우터가 꺼져 있어도 헬스체크용으로 구성해 둔다)
db_router = DatabaseRouter(
    writer=engine,
    readers=read_engines,
    sticky_after_write=db_settings.DB_READ_STICKY_AFTER_WRITE,
)


# =============================================================================
# 메인 세션 팩토리 (FastAPI DI용)
# =============================================================================
# - expire_on_commit=False: 커밋 후에도 객체 속성 접근 가능
# - autoflush=False: 명시적 flush 권장 (예측 가능한 쿼리 타이밍)
#
# 라우터가 켜져 있으면 RoutingSession 이 구문마다 엔진을 고르고,
# 꺼져 있으면 단일 엔진에 직접 바인딩한다(오버헤드·동작 모두 기존 그대로).
if db_settings.DB_ROUTER_ENABLED:
    AsyncSessionLocal = create_routing_sessionmaker(db_router)
else:
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

# 기동 시 라우팅 구성을 한 줄로 남긴다 (비밀번호는 config.mask_dsn 이 마스킹).
logger.info("[database] 라우팅 구성: %s", db_settings.describe_routing())


# =============================================================================
# 백그라운드 태스크 전용 엔진 (메인 풀과 분리)
# =============================================================================
# 백그라운드 작업(로그 저장, 비동기 처리 등)용 별도 커넥션 풀
# 메인 API 요청과 분리하여 풀 고갈 방지
#
# 백그라운드 작업은 대부분 쓰기(접속 로그 적재 등)이므로 primary 에 직접 붙인다.
# 라우팅을 태우지 않는 편이 예측 가능하고, replica 로 새는 사고도 없다.
background_engine = create_async_engine(
    url=db_settings.MYSQL_WRITER_URL,
    echo=False,
    pool_size=10,  # 백그라운드용은 작게 설정
    max_overflow=10,
    pool_timeout=60,  # 백그라운드는 대기 시간 여유있게
    pool_recycle=280,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
    connect_args={
        "connect_timeout": 10,
        "charset": "utf8mb4",
    },
)

# 백그라운드 세션 팩토리
BackgroundSessionLocal = async_sessionmaker(
    bind=background_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def background_db_session() -> AsyncGenerator[AsyncSession, None]:
    """요청 밖(백그라운드 태스크·Celery)에서 사용하는 DB 세션 컨텍스트.

    요청 스코프 DI 를 쓸 수 없는 곳에서 트랜잭션 경계를 제공한다.
    예외 시 롤백하고, 컨텍스트 종료 시 세션을 닫는다. 커밋은 호출자가 명시한다.

    Example:
        async with background_db_session() as db_session:
            await SomeService(db_session).do_write()
            await db_session.commit()
    """
    async with BackgroundSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def create_db_tables(import_models: bool = True) -> None:
    """
    데이터베이스 테이블을 생성합니다.

    애플리케이션 시작 시 자원 관리자(app/core/resources.py)에서 호출됩니다.

    Args:
        import_models: 모델 모듈을 여기서 import 할지 여부. 호출자가 이미
            ``import_all_models()`` 를 실행해 ``Base.metadata`` 를 채웠다면
            ``False`` 를 준다. 같은 startup 에서 discovery 를 두 번 돌리면
            로그의 모듈 수·소요 시간이 실제와 어긋난다(AR-007).

    Note:
        모델 import 목록은 app/core/db/models_registry.py 가 디렉터리에서
        자동으로 판별한다. 새 기능은 app/features/<name>/ 를 만들고
        라우터는 main.py 에 명시적으로 include_router 한 줄을 추가한다.
    """
    import asyncio

    if import_models:
        from app.core.db.models_registry import import_all_models

        # 모델 메타데이터 등록: 각 앱 models 모듈 import -> Base.metadata 채움
        registered = import_all_models()
        logger.info("[database] 모델 등록: %d개 모듈 %s", len(registered), registered)

    logger.info("Creating database tables...")

    async with asyncio.timeout(30):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)


async def get_routed_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    구문에 따라 reader/writer 를 동적으로 고르는 DB 세션 (FastAPI DI)

    **명시적으로 승인된 특수 경로에서만 사용한다.** 일반 조회는
    ``get_read_only_db_session``, 쓰기는 ``get_writer_db_session`` 이다.
    동적 라우팅은 "이 핸들러가 읽기인지 쓰기인지"를 코드가 아니라 실행 시점의
    구문이 결정하게 만들어, 첫 SELECT 가 replica 로 새는 경로를 남긴다.

    요청 종료 시 자동으로 세션이 닫히고, 예외 발생 시 자동 롤백됩니다.

    Yields:
        AsyncSession: 데이터베이스 세션

    Note:
        - 세션은 요청 범위(request scope)로 관리됩니다
        - 트랜잭션 경계는 쓰기 핸들러 본문이 `await service.commit()` 으로 관리합니다
    """
    start_time = time.perf_counter()

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(
                f"[get_session] ROLLBACK - error: {type(e).__name__}: {e}, "
                f"duration: {(time.perf_counter() - start_time)*1000:.1f}ms"
            )
            raise e


async def get_read_only_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    읽기 전용 DB 세션 (FastAPI DI) — GET/HEAD 의 기본값

    라우터가 켜져 있으면 세션이 replica 에 고정되고, 쓰기를 시도하면
    ``ReadOnlyRoutingError`` 로 즉시 실패해 "읽기 전용 핸들러가 몰래 쓰는" 사고를
    코드 수준에서 차단합니다.

    Yields:
        AsyncSession: 읽기 전용 데이터베이스 세션

    Example:
        @app.get("/posts")
        async def list_posts(
            service: BlogService = Depends(get_blog_service_readonly),
        ): ...

    Note:
        - DB_ROUTER_ENABLED=false 면 라우팅·쓰기 차단이 동작하지 않고
          단일 엔진 세션을 반환합니다.
        - 복제 지연을 허용할 수 없는 읽기라면 get_writer_db_session() 을 쓰세요.
    """
    async with AsyncSessionLocal() as session:
        mark_read_only(session)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_writer_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    쓰기 DB 세션 (FastAPI DI) — POST/PUT/PATCH/DELETE 및 조회 후 쓰기의 기본값

    **첫 쿼리부터** primary 에 고정됩니다. 조회 후 쓰기 유스케이스에서 첫 SELECT
    가 replica 로 새면 복제 지연만큼 낡은 값을 읽고 그 위에 쓰게 됩니다.

    Yields:
        AsyncSession: primary 에 고정된 데이터베이스 세션
    """
    async with AsyncSessionLocal() as session:
        using_writer(session)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_background_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    백그라운드 태스크용 DB 세션 (FastAPI DI)

    메인 커넥션 풀과 분리된 백그라운드 풀을 사용합니다.

    Yields:
        AsyncSession: 백그라운드 작업용 데이터베이스 세션

    Note:
        - 메인 API 풀과 분리되어 있어 백그라운드 작업이 API를 블로킹하지 않습니다
        - 요청 밖 트랜잭션 경계는 background_db_session() 컨텍스트를 권장합니다
    """
    start_time = time.perf_counter()

    async with BackgroundSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(
                f"[get_background_session] ROLLBACK - "
                f"error: {type(e).__name__}: {e}, "
                f"duration: {(time.perf_counter() - start_time)*1000:.1f}ms"
            )
            raise e


async def dispose_engine() -> None:
    """
    앱 종료 시 엔진 리소스 정리

    lifespan의 shutdown 단계에서 호출됩니다.
    모든 커넥션 풀을 정리하고 데이터베이스 연결을 종료합니다.

    Note:
        이 함수가 호출되지 않으면 커넥션이 정리되지 않아
        데이터베이스에 좀비 연결이 남을 수 있습니다.
    """
    logger.info("[dispose_engine] Disposing database engines...")
    await engine.dispose()
    logger.info("[dispose_engine] Main engine disposed")

    # replica 엔진도 함께 정리한다 (복제 비활성이면 빈 목록이라 no-op).
    for index, read_engine in enumerate(read_engines):
        await read_engine.dispose()
        logger.info("[dispose_engine] Read replica engine #%d disposed", index)

    await background_engine.dispose()
    logger.info("[dispose_engine] Background engine disposed - ALL DONE")


# =============================================================================
# Deprecated 별칭 — 호출부 전환 기간에만 유지한다 (TX-005 / MIG-002 단계 9)
# =============================================================================
# 새 이름이 정식 API 다. 옛 이름은 **같은 함수 객체**를 가리키게 둔다 — 별도 래퍼로
# 감싸면 FastAPI 의 의존성 캐시 키(callable 자체)가 달라져, 전환 중 한 요청에서
# 세션이 둘로 갈라진다. 전체 호출부 전환과 사용처 0건 확인 후 별도 단계에서 지운다.
get_session = get_routed_db_session
get_read_session = get_read_only_db_session
get_write_session = get_writer_db_session
get_background_session = get_background_db_session
background_session = background_db_session
