"""
데이터베이스 세션 및 엔진 관리 모듈

SQLAlchemy 비동기 엔진과 세션 팩토리를 설정합니다.

주요 구성요소:
    - engine: FastAPI 요청 처리용 메인 엔진 (pool_size=20, max_overflow=20)
    - background_engine: 백그라운드 태스크용 분리 엔진 (pool_size=10, max_overflow=10)
    - AsyncSessionLocal: 메인 세션 팩토리
    - BackgroundSessionLocal: 백그라운드 세션 팩토리
    - get_session(): FastAPI DI용 세션 제너레이터
    - get_background_session(): 백그라운드 태스크용 세션 제너레이터

커넥션 풀 분리 이유:
    백그라운드 태스크(예: 접속 로그 저장)가 메인 API 요청의 커넥션 풀을
    고갈시키지 않도록 별도의 풀을 사용합니다.

사용 예시:
    # FastAPI 엔드포인트에서
    @app.get("/users")
    async def get_users(session: AsyncSession = Depends(get_session)):
        result = await session.execute(select(User))
        return result.scalars().all()

    # 백그라운드 태스크에서
    async def save_log(data: dict):
        async for session in get_background_session():
            session.add(AccessLog(**data))
            await session.commit()
"""

import time
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.utils.logger import get_logger
from config import db_settings

logger = get_logger("database")


class Base(DeclarativeBase):
    """
    SQLAlchemy 선언적 베이스 클래스

    모든 ORM 모델은 이 클래스를 상속해야 합니다.

    Example:
        class User(Base):
            __tablename__ = "users"
            id: Mapped[str] = mapped_column(String(36), primary_key=True)
            name: Mapped[str] = mapped_column(String(100))
    """

    pass


# =============================================================================
# 메인 엔진 (FastAPI 요청용)
# =============================================================================
# API 요청 처리를 위한 커넥션 풀
# - pool_size: 기본 유지 연결 수 (20)
# - max_overflow: 추가 허용 연결 수 (20) → 최대 40개 동시 연결
# - pool_pre_ping: 연결 사용 전 유효성 검사 (죽은 연결 자동 복구)
# - pool_recycle: 연결 재활용 주기 (MySQL wait_timeout보다 짧게 설정)
engine = create_async_engine(
    url=db_settings.MYSQL_URL,
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

# 메인 세션 팩토리 (FastAPI DI용)
# - expire_on_commit=False: 커밋 후에도 객체 속성 접근 가능
# - autoflush=False: 명시적 flush 권장 (예측 가능한 쿼리 타이밍)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# =============================================================================
# 백그라운드 태스크 전용 엔진 (메인 풀과 분리)
# =============================================================================
# 백그라운드 작업(로그 저장, 비동기 처리 등)용 별도 커넥션 풀
# 메인 API 요청과 분리하여 풀 고갈 방지
background_engine = create_async_engine(
    url=db_settings.MYSQL_URL,
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


async def create_db_tables() -> None:
    """
    데이터베이스 테이블을 생성합니다.

    애플리케이션 시작 시 lifespan에서 호출됩니다.
    모델 클래스를 import하여 메타데이터에 등록한 후 테이블을 생성합니다.

    Note:
        새로운 모델을 추가할 때는 아래 import 목록에 추가해야 합니다.
    """
    import asyncio

    # =========================================================================
    # 모델 import (테이블 메타데이터 등록)
    # 새로운 모델 추가 시 여기에 import 추가
    # =========================================================================
    from app.home.models.models import UserAccessLog  # noqa: F401

    # 생성할 테이블 목록
    tables_to_create = [
        UserAccessLog.__table__,
        # 새 테이블 추가 시 여기에 추가
    ]

    logger.info("Creating database tables...")

    async with asyncio.timeout(10):  # 10초 타임아웃
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=tables_to_create)
            )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 의존성 주입용 세션 제너레이터

    FastAPI 엔드포인트에서 Depends()로 사용합니다.
    요청 종료 시 자동으로 세션이 닫힙니다.
    예외 발생 시 자동 롤백됩니다.

    Yields:
        AsyncSession: 데이터베이스 세션

    Example:
        @app.get("/users/{id}")
        async def get_user(
            id: str,
            session: AsyncSession = Depends(get_session)
        ):
            user = await session.get(User, id)
            return user

    Note:
        - 세션은 요청 범위(request scope)로 관리됩니다
        - 한 요청 내에서 여러 번 호출해도 같은 세션을 반환하지 않습니다
        - 트랜잭션 관리는 UnitOfWork 패턴 사용을 권장합니다
    """
    start_time = time.perf_counter()
    pool = engine.pool

    # 커넥션 풀 상태 로깅 (디버깅용 - 필요 시 주석 해제)
    # logger.debug(
    #     f"[get_session] ACQUIRE - pool_size: {pool.size()}, "
    #     f"in: {pool.checkedin()}, out: {pool.checkedout()}, "
    #     f"overflow: {pool.overflow()}"
    # )

    async with AsyncSessionLocal() as session:
        acquire_time = time.perf_counter()
        # logger.debug(
        #     f"[get_session] Session acquired in "
        #     f"{(acquire_time - start_time)*1000:.1f}ms"
        # )
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(
                f"[get_session] ROLLBACK - error: {type(e).__name__}: {e}, "
                f"duration: {(time.perf_counter() - start_time)*1000:.1f}ms"
            )
            raise e
        finally:
            total_time = time.perf_counter() - start_time
            # logger.debug(
            #     f"[get_session] RELEASE - duration: {total_time*1000:.1f}ms, "
            #     f"pool_out: {pool.checkedout()}"
            # )


async def get_background_session() -> AsyncGenerator[AsyncSession, None]:
    """
    백그라운드 태스크용 세션 제너레이터

    메인 커넥션 풀과 분리된 백그라운드 풀을 사용합니다.
    asyncio.create_task() 등으로 생성된 백그라운드 작업에서 사용합니다.

    Yields:
        AsyncSession: 백그라운드 작업용 데이터베이스 세션

    Example:
        async def save_access_log(data: dict):
            async for session in get_background_session():
                log = UserAccessLog(**data)
                session.add(log)
                await session.commit()

    Note:
        - 메인 API 풀과 분리되어 있어 백그라운드 작업이 API를 블로킹하지 않습니다
        - BackgroundUnitOfWork 사용을 권장합니다
    """
    start_time = time.perf_counter()
    pool = background_engine.pool

    # logger.debug(
    #     f"[get_background_session] ACQUIRE - pool_size: {pool.size()}, "
    #     f"in: {pool.checkedin()}, out: {pool.checkedout()}, "
    #     f"overflow: {pool.overflow()}"
    # )

    async with BackgroundSessionLocal() as session:
        acquire_time = time.perf_counter()
        # logger.debug(
        #     f"[get_background_session] Session acquired in "
        #     f"{(acquire_time - start_time)*1000:.1f}ms"
        # )
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
        finally:
            total_time = time.perf_counter() - start_time
            # logger.debug(
            #     f"[get_background_session] RELEASE - "
            #     f"duration: {total_time*1000:.1f}ms, "
            #     f"pool_out: {pool.checkedout()}"
            # )


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
    await background_engine.dispose()
    logger.info("[dispose_engine] Background engine disposed - ALL DONE")
