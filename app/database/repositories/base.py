"""
기본 Repository 클래스

모든 Repository의 기반이 되는 Generic 클래스입니다.
CRUD 작업과 N+1 문제 해결을 위한 Eager Loading 메서드를 제공합니다.

사용법:
    class UserRepository(BaseRepository[User]):
        model = User

    # 기본 CRUD
    user = await repo.create({"name": "John"})
    user = await repo.get_by_id("id")
    users = await repo.get_all()

    # N+1 해결 - Eager Loading
    user = await repo.get_by_id_with("id", relations=["posts", "profile"])
    users = await repo.get_all_with(relations=["posts"])
"""

from typing import Any, Generic, Sequence, TypeVar
from uuid import uuid4

from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    joinedload,
    selectinload,
    subqueryload,
    load_only,
    contains_eager,
    defer,
)
from sqlalchemy.sql import Select

from app.core.exception import DatabaseException, DuplicateException, NotFoundException
from app.database.session import Base
from app.utils.logger import get_logger

logger = get_logger("repository")

# Generic 타입 변수: Base를 상속한 모든 SQLAlchemy 모델을 받을 수 있음
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    기본 Repository 클래스

    SQLAlchemy 모델에 대한 CRUD 작업과 N+1 문제 해결을 위한
    Eager Loading 메서드를 제공합니다.

    Attributes:
        model: SQLAlchemy 모델 클래스 (하위 클래스에서 정의)
        session: 비동기 데이터베이스 세션

    Type Parameters:
        ModelType: Base를 상속한 SQLAlchemy 모델 타입

    Example:
        class UserRepository(BaseRepository[User]):
            model = User

        repo = UserRepository(session)
        user = await repo.get_by_id("123")  # 타입: User | None
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        """
        BaseRepository 초기화

        Args:
            session: 비동기 데이터베이스 세션 (AsyncSession)
        """
        self.session = session

    # ========================================================================
    # LOADING STRATEGY HELPERS (내부 헬퍼 메서드)
    # ========================================================================

    def _apply_eager_loading(
        self,
        stmt: Select,
        relations: list[str] | None = None,
        strategy: str = "selectin",
    ) -> Select:
        """
        Eager Loading 전략을 쿼리에 적용합니다.

        N+1 문제를 해결하기 위해 관계 데이터를 미리 로드합니다.

        Args:
            stmt: SQLAlchemy Select 문
            relations: 로드할 관계 필드 목록 (예: ["posts", "comments"])
            strategy: 로딩 전략
                - "selectin": SELECT ... WHERE id IN (...) - 1:N 컬렉션에 권장
                - "joined": LEFT JOIN으로 한 번에 조회 - 1:1, N:1에 권장
                - "subquery": 서브쿼리 사용 - selectin과 유사

        Returns:
            Eager Loading이 적용된 Select 문

        Note:
            중첩 관계도 지원합니다: "posts.comments" -> posts와 그 comments 로드
        """
        if not relations:
            return stmt

        loader_map = {
            "selectin": selectinload,
            "joined": joinedload,
            "subquery": subqueryload,
        }
        loader = loader_map.get(strategy, selectinload)

        for relation in relations:
            # 중첩 관계 지원: "posts.comments" -> posts -> comments
            parts = relation.split(".")
            load_option = loader(getattr(self.model, parts[0]))

            for part in parts[1:]:
                load_option = load_option.selectinload(part)

            stmt = stmt.options(load_option)

        return stmt

    def _apply_column_loading(
        self,
        stmt: Select,
        only_columns: list[str] | None = None,
        defer_columns: list[str] | None = None,
    ) -> Select:
        """
        컬럼 레벨 로딩을 적용합니다 (부분 로딩).

        대용량 컬럼(TEXT, BLOB 등)을 제외하여 성능을 최적화합니다.

        Args:
            stmt: SQLAlchemy Select 문
            only_columns: 로드할 컬럼만 지정 (나머지는 지연 로딩)
            defer_columns: 지연 로딩할 컬럼 지정

        Returns:
            컬럼 로딩이 적용된 Select 문
        """
        if only_columns:
            columns = [getattr(self.model, col) for col in only_columns]
            stmt = stmt.options(load_only(*columns))

        if defer_columns:
            for col in defer_columns:
                stmt = stmt.options(defer(getattr(self.model, col)))

        return stmt

    # ========================================================================
    # CREATE (생성)
    # ========================================================================

    async def create(self, data: dict[str, Any]) -> ModelType:
        """
        새로운 레코드를 생성합니다.

        Args:
            data: 생성할 데이터 딕셔너리

        Returns:
            생성된 모델 인스턴스

        Raises:
            DuplicateException: 중복 데이터가 존재하는 경우
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            user = await repo.create({"name": "John", "email": "john@example.com"})
        """
        if "id" not in data:
            data["id"] = str(uuid4())

        try:
            instance = self.model(**data)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            return instance
        except IntegrityError as e:
            logger.error(f"[CREATE] 중복 데이터 오류: {e}")
            raise DuplicateException(
                message="이미 존재하는 데이터입니다.",
                detail={"model": self.model.__name__, "error": str(e.orig)},
            ) from e
        except SQLAlchemyError as e:
            logger.error(f"[CREATE] 데이터베이스 오류: {e}")
            raise DatabaseException(
                message="데이터 생성 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__, "error": str(e)},
            ) from e

    async def bulk_create(self, data_list: list[dict[str, Any]]) -> list[ModelType]:
        """
        여러 레코드를 일괄 생성합니다.

        Args:
            data_list: 생성할 데이터 딕셔너리 목록

        Returns:
            생성된 모델 인스턴스 목록

        Raises:
            DuplicateException: 중복 데이터가 존재하는 경우
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            users = await repo.bulk_create([
                {"name": "John"},
                {"name": "Jane"},
            ])
        """
        try:
            instances = []
            for data in data_list:
                if "id" not in data:
                    data["id"] = str(uuid4())
                instances.append(self.model(**data))

            self.session.add_all(instances)
            await self.session.flush()

            for instance in instances:
                await self.session.refresh(instance)

            return instances
        except IntegrityError as e:
            logger.error(f"[BULK_CREATE] 중복 데이터 오류: {e}")
            raise DuplicateException(
                message="일괄 생성 중 중복 데이터가 발견되었습니다.",
                detail={"model": self.model.__name__, "error": str(e.orig)},
            ) from e
        except SQLAlchemyError as e:
            logger.error(f"[BULK_CREATE] 데이터베이스 오류: {e}")
            raise DatabaseException(
                message="일괄 데이터 생성 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__, "error": str(e)},
            ) from e

    # ========================================================================
    # READ - 기본 조회
    # ========================================================================

    async def get_by_id(self, id: str) -> ModelType | None:
        """
        ID로 레코드를 조회합니다.

        Args:
            id: 조회할 레코드의 ID

        Returns:
            모델 인스턴스 또는 None

        Example:
            user = await repo.get_by_id("550e8400-e29b-41d4-a716-446655440000")
        """
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, id: str) -> ModelType:
        """
        ID로 레코드를 조회하고, 없으면 예외를 발생시킵니다.

        Args:
            id: 조회할 레코드의 ID

        Returns:
            모델 인스턴스

        Raises:
            NotFoundException: 레코드가 존재하지 않는 경우

        Example:
            user = await repo.get_by_id_or_raise("user-123")  # 없으면 예외 발생
        """
        instance = await self.get_by_id(id)
        if instance is None:
            raise NotFoundException(
                message=f"{self.model.__name__}을(를) 찾을 수 없습니다.",
                detail={"model": self.model.__name__, "id": id},
            )
        return instance

    async def get_one(self, **filters: Any) -> ModelType | None:
        """
        필터 조건으로 단일 레코드를 조회합니다.

        Args:
            **filters: 필터 조건 (컬럼명=값)

        Returns:
            모델 인스턴스 또는 None

        Example:
            user = await repo.get_one(email="john@example.com")
        """
        stmt = select(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many(
        self,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Sequence[ModelType]:
        """
        필터 조건으로 여러 레코드를 조회합니다.

        Args:
            skip: 건너뛸 레코드 수 (offset)
            limit: 최대 조회 수
            **filters: 필터 조건 (컬럼명=값)

        Returns:
            모델 인스턴스 목록

        Example:
            active_users = await repo.get_many(is_active=True, limit=50)
        """
        stmt = select(self.model).filter_by(**filters).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        """
        모든 레코드를 조회합니다.

        Args:
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            모델 인스턴스 목록

        Example:
            users = await repo.get_all(skip=0, limit=100)
        """
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        """
        레코드 수를 반환합니다.

        Args:
            **filters: 필터 조건 (선택적)

        Returns:
            레코드 수

        Example:
            total = await repo.count()
            active_count = await repo.count(is_active=True)
        """
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: str) -> bool:
        """
        ID로 레코드 존재 여부를 확인합니다.

        Args:
            id: 확인할 레코드의 ID

        Returns:
            존재 여부 (True/False)

        Example:
            if await repo.exists("user-123"):
                print("User exists")
        """
        stmt = select(func.count()).select_from(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def exists_by(self, **filters: Any) -> bool:
        """
        필터 조건으로 레코드 존재 여부를 확인합니다.

        Args:
            **filters: 필터 조건

        Returns:
            존재 여부 (True/False)

        Example:
            if await repo.exists_by(email="john@example.com"):
                print("Email already exists")
        """
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    # ========================================================================
    # READ - Eager Loading (N+1 문제 해결)
    # ========================================================================

    async def get_by_id_with(
        self,
        id: str,
        relations: list[str] | None = None,
        strategy: str = "selectin",
    ) -> ModelType | None:
        """
        ID로 조회하면서 관계 데이터를 함께 로드합니다.

        N+1 문제를 방지하여 관계 데이터에 접근할 때 추가 쿼리가 발생하지 않습니다.

        Args:
            id: 조회할 레코드 ID
            relations: 함께 로드할 관계 목록 (예: ["posts", "profile"])
            strategy: 로딩 전략 ("selectin", "joined", "subquery")

        Returns:
            관계가 로드된 모델 인스턴스 또는 None

        Example:
            user = await repo.get_by_id_with(
                id="user-123",
                relations=["posts", "profile"],
                strategy="joined"
            )
            print(user.posts)  # 추가 쿼리 없음
        """
        stmt = select(self.model).where(self.model.id == id)
        stmt = self._apply_eager_loading(stmt, relations, strategy)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_one_with(
        self,
        relations: list[str] | None = None,
        strategy: str = "selectin",
        **filters: Any,
    ) -> ModelType | None:
        """
        필터 조건으로 단일 조회하면서 관계를 함께 로드합니다.

        Args:
            relations: 함께 로드할 관계 목록
            strategy: 로딩 전략
            **filters: 필터 조건

        Returns:
            관계가 로드된 모델 인스턴스 또는 None

        Example:
            user = await repo.get_one_with(
                relations=["posts"],
                email="john@example.com"
            )
        """
        stmt = select(self.model).filter_by(**filters)
        stmt = self._apply_eager_loading(stmt, relations, strategy)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many_with(
        self,
        relations: list[str] | None = None,
        strategy: str = "selectin",
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Sequence[ModelType]:
        """
        여러 레코드를 관계 데이터와 함께 조회합니다.

        Args:
            relations: 함께 로드할 관계 목록
            strategy: 로딩 전략
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수
            **filters: 필터 조건

        Returns:
            관계가 로드된 모델 인스턴스 목록

        Example:
            users = await repo.get_many_with(
                relations=["posts", "posts.comments"],  # 중첩 관계
                is_active=True,
                limit=50
            )
        """
        stmt = select(self.model).filter_by(**filters).offset(skip).limit(limit)
        stmt = self._apply_eager_loading(stmt, relations, strategy)

        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def get_all_with(
        self,
        relations: list[str] | None = None,
        strategy: str = "selectin",
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        """
        전체 레코드를 관계 데이터와 함께 조회합니다.

        Args:
            relations: 함께 로드할 관계 목록
            strategy: 로딩 전략
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            관계가 로드된 모델 인스턴스 목록

        Example:
            users = await repo.get_all_with(
                relations=["profile", "posts"],
                strategy="selectin",
                limit=100
            )
        """
        stmt = select(self.model).offset(skip).limit(limit)
        stmt = self._apply_eager_loading(stmt, relations, strategy)

        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def get_by_ids_with(
        self,
        ids: list[str],
        relations: list[str] | None = None,
        strategy: str = "selectin",
    ) -> Sequence[ModelType]:
        """
        여러 ID를 한 번에 조회하면서 관계도 함께 로드합니다.

        Args:
            ids: 조회할 ID 목록
            relations: 함께 로드할 관계 목록
            strategy: 로딩 전략

        Returns:
            관계가 로드된 모델 인스턴스 목록

        Example:
            users = await repo.get_by_ids_with(
                ids=["id1", "id2", "id3"],
                relations=["posts", "profile"]
            )
        """
        if not ids:
            return []

        stmt = select(self.model).where(self.model.id.in_(ids))
        stmt = self._apply_eager_loading(stmt, relations, strategy)

        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    # ========================================================================
    # READ - Partial Loading (컬럼 최적화)
    # ========================================================================

    async def get_partial(
        self,
        columns: list[str],
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Sequence[ModelType]:
        """
        필요한 컬럼만 선택적으로 조회합니다.

        대용량 컬럼(TEXT, BLOB 등)을 제외하여 성능을 최적화합니다.

        Args:
            columns: 로드할 컬럼 목록
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수
            **filters: 필터 조건

        Returns:
            부분 로드된 모델 인스턴스 목록

        Example:
            # content 컬럼 제외하고 조회 (목록용)
            posts = await repo.get_partial(
                columns=["id", "title", "created_at"],
                is_published=True
            )
        """
        stmt = select(self.model).filter_by(**filters).offset(skip).limit(limit)
        stmt = self._apply_column_loading(stmt, only_columns=columns)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_id_partial(
        self,
        id: str,
        columns: list[str],
    ) -> ModelType | None:
        """
        ID로 조회하면서 필요한 컬럼만 로드합니다.

        Args:
            id: 조회할 레코드 ID
            columns: 로드할 컬럼 목록

        Returns:
            부분 로드된 모델 인스턴스 또는 None

        Example:
            post = await repo.get_by_id_partial(
                id="post-123",
                columns=["id", "title", "author_id"]
            )
        """
        stmt = select(self.model).where(self.model.id == id)
        stmt = self._apply_column_loading(stmt, only_columns=columns)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # READ - Batch Loading (배치 처리)
    # ========================================================================

    async def get_in_batches(
        self,
        batch_size: int = 100,
        relations: list[str] | None = None,
        **filters: Any,
    ):
        """
        대용량 데이터를 배치로 조회합니다 (Async Generator).

        메모리 효율적인 대용량 처리를 위한 메서드입니다.

        Args:
            batch_size: 배치 크기
            relations: 함께 로드할 관계 목록
            **filters: 필터 조건

        Yields:
            배치 단위 모델 인스턴스 목록

        Example:
            async for batch in repo.get_in_batches(batch_size=100):
                for user in batch:
                    await process(user)
        """
        offset = 0

        while True:
            stmt = (
                select(self.model)
                .filter_by(**filters)
                .offset(offset)
                .limit(batch_size)
            )
            stmt = self._apply_eager_loading(stmt, relations)

            result = await self.session.execute(stmt)
            batch = result.scalars().unique().all()

            if not batch:
                break

            yield batch
            offset += batch_size

    # ========================================================================
    # READ - Join (명시적 조인)
    # ========================================================================

    async def get_with_join(
        self,
        join_model: type,
        join_condition: Any,
        relations: list[str] | None = None,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Sequence[ModelType]:
        """
        명시적 JOIN으로 조회합니다.

        Args:
            join_model: JOIN할 모델 클래스
            join_condition: JOIN 조건
            relations: contains_eager로 로드할 관계
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수
            **filters: 필터 조건

        Returns:
            JOIN 결과 모델 인스턴스 목록

        Example:
            users = await user_repo.get_with_join(
                join_model=Post,
                join_condition=User.id == Post.author_id,
                relations=["posts"]
            )
        """
        stmt = (
            select(self.model)
            .join(join_model, join_condition)
            .filter_by(**filters)
            .offset(skip)
            .limit(limit)
        )

        # contains_eager: 이미 JOIN한 데이터를 관계에 매핑
        if relations:
            for relation in relations:
                stmt = stmt.options(contains_eager(getattr(self.model, relation)))

        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    # ========================================================================
    # READ - Aggregation (집계)
    # ========================================================================

    async def count_with_relation(
        self,
        relation: str,
        **filters: Any,
    ) -> list[tuple[ModelType, int]]:
        """
        관계 데이터의 개수와 함께 조회합니다.

        Args:
            relation: 카운트할 관계 이름
            **filters: 필터 조건

        Returns:
            (모델 인스턴스, 관계 개수) 튜플 목록

        Example:
            results = await user_repo.count_with_relation("posts")
            for user, post_count in results:
                print(f"{user.name}: {post_count} posts")
        """
        relation_attr = getattr(self.model, relation)
        relation_model = relation_attr.property.mapper.class_

        stmt = (
            select(self.model, func.count(relation_model.id).label("count"))
            .outerjoin(relation_attr)
            .filter_by(**filters)
            .group_by(self.model.id)
        )

        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    # ========================================================================
    # UPDATE (수정)
    # ========================================================================

    async def update(self, id: str, data: dict[str, Any]) -> ModelType | None:
        """
        ID로 레코드를 업데이트합니다.

        Args:
            id: 업데이트할 레코드의 ID
            data: 업데이트할 데이터 딕셔너리

        Returns:
            업데이트된 모델 인스턴스 또는 None

        Raises:
            DuplicateException: 중복 데이터로 인한 제약 조건 위반
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            user = await repo.update("user-123", {"name": "New Name"})
        """
        try:
            stmt = (
                update(self.model)
                .where(self.model.id == id)
                .values(**data)
                .returning(self.model)
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.scalar_one_or_none()
        except IntegrityError as e:
            logger.error(f"[UPDATE] 무결성 제약 조건 위반: {e}")
            raise DuplicateException(
                message="업데이트할 데이터가 기존 데이터와 충돌합니다.",
                detail={"model": self.model.__name__, "id": id, "error": str(e.orig)},
            ) from e
        except SQLAlchemyError as e:
            logger.error(f"[UPDATE] 데이터베이스 오류: {e}")
            raise DatabaseException(
                message="데이터 업데이트 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__, "id": id, "error": str(e)},
            ) from e

    async def bulk_update(
        self,
        ids: list[str],
        data: dict[str, Any],
    ) -> int:
        """
        여러 레코드를 일괄 업데이트합니다.

        Args:
            ids: 업데이트할 레코드 ID 목록
            data: 업데이트할 데이터 딕셔너리

        Returns:
            업데이트된 레코드 수

        Example:
            count = await repo.bulk_update(
                ids=["id1", "id2", "id3"],
                data={"is_active": False}
            )
        """
        stmt = (
            update(self.model)
            .where(self.model.id.in_(ids))
            .values(**data)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def update_by(
        self,
        data: dict[str, Any],
        **filters: Any,
    ) -> int:
        """
        필터 조건에 맞는 레코드를 업데이트합니다.

        Args:
            data: 업데이트할 데이터 딕셔너리
            **filters: 필터 조건

        Returns:
            업데이트된 레코드 수

        Example:
            count = await repo.update_by(
                data={"is_active": False},
                role="guest"
            )
        """
        stmt = (
            update(self.model)
            .filter_by(**filters)
            .values(**data)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    # ========================================================================
    # DELETE (삭제)
    # ========================================================================

    async def delete(self, id: str) -> bool:
        """
        ID로 레코드를 삭제합니다.

        Args:
            id: 삭제할 레코드의 ID

        Returns:
            삭제 성공 여부 (True/False)

        Raises:
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            if await repo.delete("user-123"):
                print("User deleted")
        """
        try:
            stmt = delete(self.model).where(self.model.id == id)
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount > 0
        except IntegrityError as e:
            logger.error(f"[DELETE] 무결성 제약 조건 위반 (참조 중인 데이터): {e}")
            raise DatabaseException(
                message="다른 데이터에서 참조 중이어서 삭제할 수 없습니다.",
                detail={"model": self.model.__name__, "id": id, "error": str(e.orig)},
            ) from e
        except SQLAlchemyError as e:
            logger.error(f"[DELETE] 데이터베이스 오류: {e}")
            raise DatabaseException(
                message="데이터 삭제 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__, "id": id, "error": str(e)},
            ) from e

    async def bulk_delete(self, ids: list[str]) -> int:
        """
        여러 레코드를 일괄 삭제합니다.

        Args:
            ids: 삭제할 레코드 ID 목록

        Returns:
            삭제된 레코드 수

        Example:
            count = await repo.bulk_delete(["id1", "id2", "id3"])
        """
        stmt = delete(self.model).where(self.model.id.in_(ids))
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete_by(self, **filters: Any) -> int:
        """
        필터 조건에 맞는 레코드를 삭제합니다.

        Args:
            **filters: 필터 조건

        Returns:
            삭제된 레코드 수

        Example:
            count = await repo.delete_by(is_expired=True)
        """
        stmt = delete(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    # ========================================================================
    # UPSERT (생성 또는 수정)
    # ========================================================================

    async def get_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **filters: Any,
    ) -> tuple[ModelType, bool]:
        """
        있으면 조회, 없으면 생성합니다.

        Args:
            defaults: 생성 시 추가할 기본값
            **filters: 조회 조건 (및 생성 시 기본 데이터)

        Returns:
            (인스턴스, 생성여부) 튜플
            - 생성여부: True면 새로 생성됨, False면 기존 데이터

        Example:
            user, created = await repo.get_or_create(
                defaults={"role": "user"},
                email="john@example.com"
            )
            if created:
                print("New user created")
        """
        instance = await self.get_one(**filters)
        if instance:
            return instance, False

        data = {**filters, **(defaults or {})}
        instance = await self.create(data)
        return instance, True

    async def update_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **filters: Any,
    ) -> tuple[ModelType, bool]:
        """
        있으면 업데이트, 없으면 생성합니다 (Upsert).

        Args:
            defaults: 업데이트/생성할 데이터
            **filters: 조회 조건

        Returns:
            (인스턴스, 생성여부) 튜플
            - 생성여부: True면 새로 생성됨, False면 업데이트됨

        Example:
            user, created = await repo.update_or_create(
                defaults={"last_login": datetime.now()},
                email="john@example.com"
            )
        """
        instance = await self.get_one(**filters)
        if instance:
            for key, value in (defaults or {}).items():
                setattr(instance, key, value)
            await self.session.flush()
            await self.session.refresh(instance)
            return instance, False

        data = {**filters, **(defaults or {})}
        instance = await self.create(data)
        return instance, True
