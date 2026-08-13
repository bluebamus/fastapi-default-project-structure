"""ORM Repository 의 안정적인 최소 공개 CRUD (ORM-REP-002).

정식 공개 API 는 아래 8개다. 이 목록이 Base 의 계약 전부이며, 여기 없는 쿼리는
**기능 Repository 가 명시적 메서드로 소유한다**::

    create(data)                생성
    get_by_id(pk)               PK 조회 (없으면 None)
    get_by_id_or_raise(pk)      PK 조회 (없으면 NotFoundException)
    list(skip, limit)           페이지네이션 목록
    count(**filters)            개수
    exists(pk)                  존재 확인 (SQL EXISTS)
    update_by_id(pk, changes)   부분 수정 (없으면 None)
    delete_by_id(pk)            삭제 (삭제 여부 반환)

왜 이렇게 좁히나:
    eager loading·join·부분 컬럼·batch 를 문자열 관계명으로 받는 범용 API 는
    오타를 실행 시점에만 드러내고, "무엇이든 할 수 있는" Base 는 도메인 지식이
    Base 로 새어 들어오는 통로가 된다. 실제로 이 저장소의 고급 메서드 20개는
    호출처가 0건이었다(Phase 0 조사, `baseline/survey.txt`). 공통성이 **두 개
    이상의 기능에서 실제로** 확인되면 그때 별도 Mixin 으로 올린다(ORM-REP-005).

트랜잭션:
    이 계층은 ``flush`` 까지만 한다. 커밋은 쓰기 View 본문이 응답 직전에
    정확히 한 번 수행한다(TX-004).

예외 정책 (ORM-REP-006):
    모든 공개 경로가 같은 변환을 거친다. 무결성 충돌은 ``DuplicateException``,
    그 밖의 SQLAlchemy 오류는 ``DatabaseException`` 이다. 원본 예외는 chaining
    으로 보존하되, **사용자에게 가는 detail 에는 원문·바인딩 파라미터를 싣지
    않는다** — 오류 응답으로 입력값이 그대로 새어나가기 때문이다(NFR-001).
    원문은 서버 로그에만 남는다.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import CursorResult, delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exception import DatabaseException, DuplicateException, NotFoundException
from app.core.repositories.crud_base import CRUDBase, ModelType
from app.utils.logs import get_logger

logger = get_logger("repository")

# PK 타입 계약. 이 저장소의 모델은 문자열 UUID 를 쓰므로 기본값을 str 로 둔다 —
# 덕분에 기존 ``BaseRepository[Model]`` 선언이 그대로 유효하다(ORM-MDL-003).
PrimaryKeyT = TypeVar("PrimaryKeyT", default=str)


class BaseRepository(CRUDBase[ModelType], Generic[ModelType, PrimaryKeyT]):
    """모델 하나에 대한 최소 공개 CRUD.

    Type Parameters:
        ModelType: Base 를 상속한 SQLAlchemy 모델 타입
        PrimaryKeyT: 기본키 타입 (기본값 ``str`` — 문자열 UUID)

    Example:
        class UserRepository(BaseRepository[User, str]):
            model = User

        # PK 가 문자열이면 두 번째 인자를 생략해도 된다.
        class PostRepository(BaseRepository[Post]):
            model = Post
    """

    model: type[ModelType]

    # ========================================================================
    # 예외 변환 (모든 공개 경로가 공유한다)
    # ========================================================================
    @contextmanager
    def _translated_errors(self, operation: str, **context: Any) -> Iterator[None]:
        """SQLAlchemy 오류를 프로젝트 예외로 바꾼다.

        detail 에 원본 메시지를 넣지 않는다. 드라이버 오류 문자열에는 위반한 값이
        그대로 들어 있어(예: 중복된 이메일) 오류 응답으로 유출된다.
        """
        try:
            yield
        except IntegrityError as error:
            logger.error(
                "[%s] 무결성 제약 위반 (model=%s): %s",
                operation.upper(),
                self.model.__name__,
                error,
            )
            raise DuplicateException(
                message="요청한 데이터가 기존 데이터와 충돌합니다.",
                detail={"model": self.model.__name__, "operation": operation, **context},
            ) from error
        except SQLAlchemyError as error:
            logger.error(
                "[%s] 데이터베이스 오류 (model=%s): %s",
                operation.upper(),
                self.model.__name__,
                error,
            )
            raise DatabaseException(
                message="데이터베이스 처리 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__, "operation": operation, **context},
            ) from error

    # ========================================================================
    # CREATE
    # ========================================================================
    async def create(self, data: dict[str, Any]) -> ModelType:
        """레코드를 생성한다.

        호출자가 넘긴 ``data`` 를 **변경하지 않는다**(ORM-REP-003). 예전 구현은
        여기서 ``data["id"]`` 를 채워 호출자 dict 를 오염시켰다. 이제 id 기본값은
        모델의 ``UUIDPrimaryKeyMixin`` 이 만든다.

        Raises:
            DuplicateException: 무결성 제약(unique/FK) 위반
            DatabaseException: 그 밖의 DB 오류
        """
        with self._translated_errors("create"):
            instance = self.model(**data)
            return await self._add(instance)

    # ========================================================================
    # READ
    # ========================================================================
    async def get_by_id(self, pk: PrimaryKeyT) -> ModelType | None:
        """PK 로 조회한다. 없으면 ``None``."""
        with self._translated_errors("get_by_id"):
            return await self._get(cast("str", pk))

    async def get_by_id_or_raise(self, pk: PrimaryKeyT) -> ModelType:
        """PK 로 조회하고 없으면 ``NotFoundException``."""
        instance = await self.get_by_id(pk)
        if instance is None:
            raise NotFoundException(
                message=f"{self.model.__name__}을(를) 찾을 수 없습니다.",
                detail={"model": self.model.__name__, "id": str(pk)},
            )
        return instance

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[ModelType]:
        """페이지 단위로 조회한다.

        ``limit`` 기본값이 있는 이유는 무제한 조회를 막기 위해서다(NFR-002).
        상한은 호출하는 View 의 Query 제약이 강제한다.
        """
        with self._translated_errors("list"):
            statement = select(self.model).offset(skip).limit(limit)
            result = await self.db_session.execute(statement)
            return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        """조건에 맞는 레코드 수."""
        with self._translated_errors("count"):
            statement = select(func.count()).select_from(self.model)
            if filters:
                statement = statement.filter_by(**filters)
            result = await self.db_session.execute(statement)
            return result.scalar_one()

    async def exists(self, pk: PrimaryKeyT) -> bool:
        """PK 존재 여부.

        ``COUNT(*)`` 는 조건에 맞는 행을 전부 세지만, ``EXISTS`` 는 첫 행에서
        멈춘다. 존재 확인의 의도와도 맞고 실행 계획도 낫다(ORM-REP-004).
        """
        with self._translated_errors("exists"):
            statement = select(exists().where(self.model.id == pk))
            result = await self.db_session.execute(statement)
            return bool(result.scalar())

    # ========================================================================
    # UPDATE
    # ========================================================================
    async def update_by_id(
        self,
        pk: PrimaryKeyT,
        changes: dict[str, Any],
    ) -> ModelType | None:
        """PK 로 부분 수정하고 갱신된 인스턴스를 돌려준다. 대상이 없으면 ``None``."""
        with self._translated_errors("update_by_id", id=str(pk)):
            statement = update(self.model).where(self.model.id == pk).values(**changes)
            result = cast("CursorResult[Any]", await self.db_session.execute(statement))
            await self._flush()

            if result.rowcount == 0:
                return None

        return await self.get_by_id(pk)

    # ========================================================================
    # DELETE
    # ========================================================================
    async def delete_by_id(self, pk: PrimaryKeyT) -> bool:
        """PK 로 삭제한다. 실제로 지워졌으면 True."""
        with self._translated_errors("delete_by_id", id=str(pk)):
            statement = delete(self.model).where(self.model.id == pk)
            result = cast("CursorResult[Any]", await self.db_session.execute(statement))
            await self._flush()
            return result.rowcount > 0

    # ========================================================================
    # Deprecated 별칭 — 호출부 전환 기간에만 유지한다 (MIG-002 단계 9 에서 제거)
    #
    # 실제 호출처가 있는 이름만 남긴다. 호출처가 0건이던 고급 메서드 20종
    # (eager loading·partial column·batch·join·bulk·upsert)은 이 단계에서
    # 제거했다 — Base 에 도메인 지식이 새어 들어오는 통로였고, 필요해지면
    # 기능 Repository 가 명시적 메서드로 소유한다(ORM-REP-005).
    # ========================================================================
    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[ModelType]:
        """Deprecated — ``list()`` 를 쓸 것."""
        return await self.list(skip=skip, limit=limit)

    async def update(self, id: PrimaryKeyT, data: dict[str, Any]) -> ModelType | None:
        """Deprecated — ``update_by_id()`` 를 쓸 것."""
        return await self.update_by_id(id, data)

    async def delete(self, id: PrimaryKeyT) -> bool:
        """Deprecated — ``delete_by_id()`` 를 쓸 것."""
        return await self.delete_by_id(id)

    async def get_one(self, **filters: Any) -> ModelType | None:
        """Deprecated — 조건 조회는 기능 Repository 의 명시적 메서드로 옮길 것.

        문자열 컬럼명을 받는 범용 필터라 오타가 실행 시점에만 드러난다.
        """
        with self._translated_errors("get_one"):
            statement = select(self.model).filter_by(**filters)
            result = await self.db_session.execute(statement)
            return result.scalar_one_or_none()
