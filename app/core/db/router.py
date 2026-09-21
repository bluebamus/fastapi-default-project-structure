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
    async def handler(db_session: AsyncSession = Depends(get_routed_db_session)):
        await session.execute(select(Post))     # → reader
        session.add(Post(...))                  # → writer (이후 세션은 writer 고정)

    # 2) 명시적 읽기 전용 — 쓰기를 시도하면 ReadOnlyRoutingError
    async def handler(db_session: AsyncSession = Depends(get_read_only_db_session)):
        await session.execute(select(Post))     # → reader

    # 3) 이스케이프 해치 — 복제 지연을 허용할 수 없는 읽기
    using_writer(session)
    await session.execute(select(Post))         # → writer

Note:
    라우터를 끄면(``DB_ROUTER_ENABLED=false``) **라우팅**은 쓰이지 않고 세션은 단일
    엔진에 직접 바인딩된다(기존 동작 그대로). 읽기 전용 세션의 쓰기 차단은 이와
    무관하게 동작한다 — 이 모듈 끝의 ``Session`` 이벤트 리스너가 집행한다.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, Select, UpdateBase, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.elements import TextClause

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


# ``text()`` 로 쓴 구문의 선두 키워드. Core 구문(UpdateBase)과 달리 타입으로는
# 읽기/쓰기를 알 수 없어 SQL 첫 단어를 본다.
#
# 오탐(읽기를 writer 로 보내는 것) 위험이 0 인 이유: 아래 단어로 **시작하는** 읽기
# 구문이 MySQL·PostgreSQL 어느 방언에도 없다. 읽기는 SELECT·WITH·SHOW·DESCRIBE·
# EXPLAIN·VALUES·TABLE 로 시작한다.
_TEXT_WRITE_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "REPLACE",
        "MERGE",
        "CREATE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "RENAME",
        "GRANT",
        "REVOKE",
        "CALL",
        "SET",
        "LOAD",  # LOAD DATA INFILE = 대량 INSERT
        "PREPARE",  # PREPARE s FROM 'INSERT...' — 선두 키워드 검사를 우회하는 유일한 실전 경로
        "EXECUTE",  # 그 PREPARE 를 실제로 실행한다
        "DEALLOCATE",  # 같은 세션 상태를 정리한다
        "LOCK",  # LOCK TABLES = 세션 상태 + writer 필수
        "UNLOCK",  # 그 잠금을 푼다
        "FLUSH",  # 서버 상태를 바꾼다
        "OPTIMIZE",  # 테이블을 재작성한다
        "REPAIR",  # 테이블을 고쳐 쓴다
        "ANALYZE",  # ANALYZE TABLE = 통계 기록 (EXPLAIN ANALYZE 는 EXPLAIN 으로 시작)
        "CHECK",  # CHECK TABLE = 락 + 일부 엔진은 복구까지 한다
        "KILL",  # 타 세션 종료
        "DO",  # MySQL `DO expr` / PostgreSQL `DO $$...$$`
    }
)

# 선행 주석(-- ... / /* ... */)과 공백을 걷어내고 첫 단어를 뽑는다.
_LEADING_NOISE = re.compile(r"^(?:\s+|--[^\n]*\n|/\*.*?\*/)+", re.DOTALL)
_FIRST_WORD = re.compile(r"^([A-Za-z_]+)")


def _text_is_write(clause: Any) -> bool:
    """``text()`` 구문이 쓰기인지 선두 키워드로 판별한다.

    ``TextClause`` 는 ``UpdateBase`` 가 아니라서 타입만 봐서는 Raw DML 을 읽기로
    오인한다. 그러면 복제가 켜져 있을 때 **UPDATE 가 replica 로 나간다**.
    (read-only 세션의 쓰기 차단은 이 함수가 아니라 아래 ``_statement_is_readable``
    경로가 맡는다 — 방향이 반대인 별개의 판정이다.)

    ponytail: 선두 키워드 판별. ``WITH ... INSERT`` 처럼 CTE 로 감싼 DML 은
    읽기로 오판한다 — 그런 SQL 을 쓰게 되면 sqlparse 같은 파서로 올린다.
    10억 건 프로덕션 쿼리 덤프 실측에서 CTE 로 감싼 DML 은 0건이었다.
    """
    sql = _LEADING_NOISE.sub("", str(clause))
    match = _FIRST_WORD.match(sql)
    if match is None:
        return False

    keyword = match.group(1).upper()
    if keyword in _TEXT_WRITE_KEYWORDS:
        return True
    # 잠금 읽기(SELECT ... FOR UPDATE)는 primary 로 가야 한다 — replica 에서 잠가도
    # 의미가 없고, 잠근 행을 곧이어 쓰는 것이 보통이다.
    return keyword == "SELECT" and "FOR UPDATE" in sql.upper()


def _is_write(clause: Any, flushing: bool) -> bool:
    """이 구문이 쓰기인지 판별한다 (ORM flush / Core DML / Raw text DML)."""
    if flushing or isinstance(clause, UpdateBase):
        return True
    return isinstance(clause, TextClause) and _text_is_write(clause)


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
                # 보통은 아래 이벤트 리스너가 먼저 잡아 여기까지 오지 않는다. 남겨 두는
                # 것은 `get_bind()` 가 `do_orm_execute`/`before_flush` 를 거치지 않는
                # 경로(예: `Session.connection()`)로도 불리기 때문이다 — 백스톱이다.
                if info.get(_READ_ONLY):
                    raise ReadOnlyRoutingError(
                        "읽기 전용 세션에서 쓰기를 시도했습니다. "
                        "쓰기에는 get_routed_db_session()/get_writer_db_session() 을 사용하세요."
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


# =============================================================================
# read-only 계약의 중앙 집행
# =============================================================================
# 예전에는 차단이 `RoutingSession.get_bind()` 안에만 있었다. `RoutingSession` 은
# `DB_ROUTER_ENABLED=true` 일 때만 만들어지므로, **기본값(false)** 과 background 세션
# 팩토리에서는 `mark_read_only()` 를 불러도 쓰기가 그대로 통과했다.
#
# read-only 는 replica 라우팅의 부산물이 아니라 **Dependency 계약**이다. 그래서 집행
# 지점을 `Session` 기반 클래스의 이벤트로 옮긴다 — 어떤 sessionmaker 로 만들었든,
# 엔진이 무엇이든 동일하게 적용된다.
#
# `session.info` 는 보안 경계가 아니다. 운영 배포는 read-only DB credential 또는
# 트랜잭션 read-only 설정을 최종 방어선으로 둔다.
#
# 주의: 위의 `_text_is_write()` 는 **라우팅 방향**(이 구문을 writer 로 보낼까)을 정하고,
# 아래 `_text_is_readable()` 은 **읽기 전용 세션의 거부 여부**를 정한다. 판정 방향이
# 반대라서 한 함수로 합치지 않는다.

_SQL_COMMENT = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)
_LOCKING_READ = re.compile(
    r"\bfor\s+(?:update|share)\b|\block\s+in\s+share\s+mode\b", re.IGNORECASE
)

# 괄호 깊이 0 에 나타나면 그 구문은 읽기가 아니다.
_TOP_LEVEL_WRITE = frozenset({"insert", "update", "delete", "replace", "merge", "into", "set"})
_READABLE_LEAD = frozenset({"select", "with"})


def is_read_only(session: Session | AsyncSession) -> bool:
    """이 세션이 읽기 전용으로 표시됐는가."""
    return bool(_session_info(session).get(_READ_ONLY))


def assert_writable(session: Session | AsyncSession, detail: str = "") -> None:
    """읽기 전용 세션이면 ``ReadOnlyRoutingError`` 를 낸다.

    Raises:
        ReadOnlyRoutingError: 세션이 read-only 로 표시돼 있을 때.
    """
    if is_read_only(session):
        raise ReadOnlyRoutingError(
            "읽기 전용 세션에서 쓰기를 시도했습니다"
            f"{f' ({detail})' if detail else ''}. "
            "쓰기에는 get_writer_db_session()/get_routed_db_session() 을 사용하세요."
        )


def _depth0_words(sql: str) -> list[str] | None:
    """따옴표·역따옴표 안을 건너뛰며 괄호 깊이 0 의 단어만 모은다.

    따옴표가 닫히지 않거나 괄호가 맞지 않으면 ``None`` — 호출부는 거부한다(fail-closed).
    """
    words: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    n = len(sql)
    while i < n:
        char = sql[i]
        if char in "'\"`":
            if buf:
                words.append("".join(buf).lower())
                buf = []
            quote = char
            i += 1
            closed = False
            while i < n:
                if sql[i] == "\\" and quote != "`":
                    i += 2
                    continue
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # '' 로 이스케이프
                        i += 2
                        continue
                    closed = True
                    break
                i += 1
            if not closed:
                return None
            i += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return None
        if char.isalnum() or char == "_":
            buf.append(char)
        else:
            if buf:
                if depth == 0:
                    words.append("".join(buf).lower())
                buf = []
        i += 1
    if buf and depth == 0:
        words.append("".join(buf).lower())
    return None if depth != 0 else words


def _text_is_readable(sql: str) -> bool:
    """Raw SQL 문자열이 **확실히** 읽기인지 판별한다(default-deny).

    parser 없이 SQL 을 완전히 분류할 수는 없다. 그래서 주석을 걷어낸 단일 문장을
    **괄호 깊이 0 의 단어**로 훑어(`_depth0_words`), 최상위 구문이 읽기임이 확실할
    때만 통과시킨다. CTE 정의는 전부 괄호 안에 있으므로 깊이 0 에 남는 단어가 곧
    최상위 구문이고, 거기 쓰기 키워드가 있으면 그 문장은 쓰기다.

    깊이 0 을 보는 이유는 **CTE 정의 뒤에 오는 최상위 키워드가 쓰기일 수 있기
    때문**이다. MySQL 8.4 기준으로 이렇다.

    - ``WITH c AS (...) SELECT ...`` — 읽기 (통과한다)
    - ``WITH c AS (...) UPDATE ...`` — **쓰기** (유효한 문법이다 → 거부)
    - ``WITH c AS (...) DELETE ...`` — **쓰기** (유효한 문법이다 → 거부)
    - ``WITH c AS (...) INSERT ...`` — 문법 오류. INSERT 는 `WITH` 로 시작할 수 없다
      (``INSERT INTO t WITH c AS (...) SELECT ...`` 형태만 유효하고, 이건 첫 토큰이
      `insert` 라 아래 검사가 이미 잡는다). `REPLACE` 도 같다.

    즉 위험 표면은 **UPDATE 와 DELETE 둘**이고, 깊이 0 스캔이 그 둘을 그대로 잡는다.
    CTE 안에 DML 을 넣는 ``WITH x AS (DELETE ... RETURNING ...)`` 은 PostgreSQL
    문법이고 MySQL 에서는 문법 오류라 이 저장소의 위협이 아니다.

    fail-closed: 따옴표가 닫히지 않거나 괄호가 맞지 않아 스캔이 무너지면 거부한다.
    판정을 넓히거나 좁히는 절차는 `docs/guides/DEVELOPMENT.md` §7.2 에 있다.
    """
    stripped = _SQL_COMMENT.sub(" ", sql).strip()
    head, separator, tail = stripped.partition(";")
    if separator and tail.strip():
        return False  # multi-statement — 뒤 문장을 검사할 수 없다
    head = head.strip()
    if not head:
        return False
    if _LOCKING_READ.search(head):
        return False  # SELECT ... FOR UPDATE 는 잠금을 잡는 쓰기 성격이다
    words = _depth0_words(head)
    if not words:
        return False  # 스캔이 무너졌거나(fail-closed) 단어가 없다
    if words[0] not in _READABLE_LEAD:
        return False
    return not any(word in _TOP_LEVEL_WRITE for word in words)


def _statement_is_readable(clause: Any) -> bool:
    """실행하려는 구문이 read-only 세션에서 허용되는지 판별한다(default-deny)."""
    if isinstance(clause, UpdateBase):
        return False  # Insert / Update / Delete / DDL
    if isinstance(clause, Select):
        return True
    if isinstance(clause, TextClause):
        return _text_is_readable(str(clause))
    return False  # 판별 불가 — 거부


@event.listens_for(Session, "before_flush")
def _block_read_only_flush(session: Session, flush_context: Any, instances: Any) -> None:
    """ORM flush(=INSERT/UPDATE/DELETE)를 read-only 세션에서 차단한다."""
    assert_writable(session, "ORM flush")


@event.listens_for(Session, "do_orm_execute")
def _block_read_only_execute(orm_execute_state: ORMExecuteState) -> None:
    """`Session.execute()` 로 나가는 모든 구문을 검사한다.

    Core DML 과 `text()` Raw SQL 이 모두 이 경계를 지난다 — 실행 지점이 하나라서
    호출부마다 검사를 흩뿌리지 않아도 된다.
    """
    if not is_read_only(orm_execute_state.session):
        return
    if not _statement_is_readable(orm_execute_state.statement):
        raise ReadOnlyRoutingError(
            "읽기 전용 세션에서 읽기로 판별되지 않는 구문을 실행하려 했습니다. "
            "SELECT 와 읽기 전용 CTE(WITH ... SELECT)만 허용되며, 최상위에 쓰기 키워드가 "
            "있거나(WITH ... UPDATE·DELETE 포함) 잠금을 획득하거나 multi-statement 이거나 "
            "따옴표·괄호가 맞지 않아 판별할 수 없는 문장은 기본 거부됩니다. "
            "쓰기에는 get_writer_db_session() 을 사용하세요."
        )
