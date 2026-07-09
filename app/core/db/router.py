"""
데이터베이스 라우터 (읽기/쓰기 분리)

Django 의 ``DATABASE_ROUTERS`` 와 같은 역할을 SQLAlchemy 에서 수행한다.
하나의 primary(writer) 서버와 0개 이상의 replica(reader) 서버를 묶어두고,
세션이 실행하는 구문의 성격에 따라 **바인딩할 엔진을 자동 선택**한다.

라우팅 규칙:
    1. ORM flush(=INSERT/UPDATE/DELETE) 또는 Core DML  → writer
    2. 그 밖의 SELECT                                   → reader (라운드로빈)
    3. 쓰기가 한 번이라도 일어난 세션의 이후 SELECT     → writer 고정(sticky)

3번(sticky)은 복제 지연(replication lag) 때문에 필요하다. 방금 커밋한 행을
곧바로 replica 에서 읽으면 아직 복제되지 않아 사라진 것처럼 보인다.
쓰기 이후에는 같은 세션을 writer 에 고정해 read-after-write 일관성을 지킨다.

한 세션이 고른 replica 는 세션이 끝날 때까지 유지된다(pin). 하나의 트랜잭션이
여러 replica 로 흩어지면 스냅샷 일관성이 깨지기 때문이다.

사용 예시:
    # 1) 투명 라우팅 — 기존 코드를 그대로 두면 알아서 갈린다
    async def handler(session: AsyncSession = Depends(get_session)):
        await session.execute(select(Post))     # → reader
        session.add(Post(...))                  # → writer (이후 세션은 writer 고정)

    # 2) 명시적 읽기 전용 — 쓰기를 시도하면 ReadOnlyRoutingError
    async def handler(session: AsyncSession = Depends(get_read_session)):
        await session.execute(select(Post))     # → reader

    # 3) 이스케이프 해치 — 복제 지연을 허용할 수 없는 읽기
    using_writer(session)
    await session.execute(select(Post))         # → writer

Note:
    라우터를 끄면(``DB_ROUTER_ENABLED=false``) 이 모듈은 쓰이지 않고
    세션은 단일 엔진에 직접 바인딩된다(기존 동작 그대로).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, UpdateBase
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

# 세션 단위 라우팅 상태를 담는 ``Session.info`` 키.
# (세션 객체에 직접 속성을 붙이지 않고 SQLAlchemy 가 제공하는 info 딕셔너리를 쓴다.)
_WRITER_PINNED = "_db_router_writer_pinned"  # 이 세션은 writer 로 고정됨
_READER_PINNED = "_db_router_reader_pinned"  # 이 세션이 선택한 replica 엔진
_READ_ONLY = "_db_router_read_only"  # 이 세션은 쓰기 금지


class ReadOnlyRoutingError(RuntimeError):
    """읽기 전용으로 표시된 세션에서 쓰기를 시도했을 때 발생한다."""


class DatabaseRouter:
    """writer 1대 + reader N대를 묶어 바인딩 대상을 결정하는 라우터.

    Args:
        writer: primary(쓰기) 엔진.
        readers: replica(읽기) 엔진 목록. 비어 있으면 읽기도 writer 로 간다.
        sticky_after_write: 쓰기 이후 같은 세션의 읽기를 writer 로 고정할지 여부.
    """

    def __init__(
        self,
        writer: AsyncEngine,
        readers: Sequence[AsyncEngine] = (),
        *,
        sticky_after_write: bool = True,
    ) -> None:
        self.writer = writer
        self.readers: list[AsyncEngine] = list(readers)
        self.sticky_after_write = sticky_after_write
        # 세션마다 하나씩 replica 를 나눠주는 라운드로빈 커서.
        self._reader_cursor = itertools.cycle(range(len(self.readers))) if self.readers else None

    @property
    def replicated(self) -> bool:
        """replica 가 하나라도 붙어 있으면 True."""
        return bool(self.readers)

    @property
    def engines(self) -> list[AsyncEngine]:
        """이 라우터가 관리하는 전체 엔진(정리·헬스체크용)."""
        return [self.writer, *self.readers]

    def next_reader(self) -> AsyncEngine:
        """다음 replica 를 라운드로빈으로 고른다. replica 가 없으면 writer 를 준다."""
        if self._reader_cursor is None:
            return self.writer
        return self.readers[next(self._reader_cursor)]


def _session_info(session: Session | AsyncSession) -> dict[Any, Any]:
    """동기/비동기 세션 어느 쪽이 와도 내부 ``info`` 딕셔너리를 돌려준다."""
    sync_session = getattr(session, "sync_session", None)
    return sync_session.info if sync_session is not None else session.info


def using_writer(session: Session | AsyncSession) -> None:
    """이 세션의 이후 모든 구문(SELECT 포함)을 writer 로 보낸다.

    복제 지연을 허용할 수 없는 읽기(예: 결제 직후 잔액 조회)에 사용한다.
    """
    _session_info(session)[_WRITER_PINNED] = True


def mark_read_only(session: Session | AsyncSession) -> None:
    """이 세션을 읽기 전용으로 표시한다. 쓰기 시도 시 ``ReadOnlyRoutingError``."""
    _session_info(session)[_READ_ONLY] = True


def _is_write(clause: Any, flushing: bool) -> bool:
    """이 구문이 쓰기인지 판별한다 (ORM flush 또는 Core INSERT/UPDATE/DELETE)."""
    return flushing or isinstance(clause, UpdateBase)


def make_routing_session_class(router: DatabaseRouter) -> type[Session]:
    """``router`` 에 묶인 ``Session`` 서브클래스를 만든다.

    ``AsyncSession`` 은 내부적으로 동기 ``Session`` 을 감싸므로, 바인딩 결정은
    동기 세션의 ``get_bind()`` 에서 이뤄지고 반환값도 동기 엔진이어야 한다
    (``AsyncEngine.sync_engine``).
    """

    class RoutingSession(Session):
        """구문 성격에 따라 writer/reader 엔진을 골라주는 세션."""

        def get_bind(
            self,
            mapper: Any = None,
            clause: Any = None,
            **kwargs: Any,
        ) -> Engine:
            info = self.info

            if _is_write(clause, self._flushing):
                if info.get(_READ_ONLY):
                    raise ReadOnlyRoutingError(
                        "읽기 전용 세션에서 쓰기를 시도했습니다. "
                        "쓰기에는 get_session()/get_write_session() 을 사용하세요."
                    )
                # 이후 SELECT 가 복제 지연에 걸리지 않도록 이 세션을 writer 에 고정한다.
                if router.sticky_after_write:
                    info[_WRITER_PINNED] = True
                return router.writer.sync_engine

            if info.get(_WRITER_PINNED):
                return router.writer.sync_engine

            # 한 세션은 한 replica 만 쓴다 — 트랜잭션이 여러 서버로 흩어지지 않도록.
            reader = info.get(_READER_PINNED)
            if reader is None:
                reader = router.next_reader()
                info[_READER_PINNED] = reader
            return reader.sync_engine

    return RoutingSession


def create_routing_sessionmaker(
    router: DatabaseRouter,
    **kwargs: Any,
) -> async_sessionmaker[AsyncSession]:
    """``router`` 의 판정에 따라 엔진을 고르는 비동기 세션 팩토리를 만든다.

    ``expire_on_commit=False`` / ``autoflush=False`` 는 기존 세션 팩토리와 동일한
    기본값이다. 특히 ``autoflush=False`` 는 라우팅과 함께 갈 때 중요하다 —
    autoflush 가 켜져 있으면 단순 SELECT 가 flush 를 유발해 세션이 writer 로
    고정되어 버려, 읽기 분산 효과가 사라진다.
    """
    kwargs.setdefault("expire_on_commit", False)
    kwargs.setdefault("autoflush", False)
    return async_sessionmaker(
        bind=router.writer,  # 기본 바인드(get_bind 가 실제 선택을 덮어쓴다)
        class_=AsyncSession,
        sync_session_class=make_routing_session_class(router),
        **kwargs,
    )
