# 서비스 레이어 구현 예시

## UserService 전체 구현

```python
"""
사용자 서비스 모듈

사용자 관련 비즈니스 로직을 처리합니다.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.security import get_password_hash, verify_password
from app.user.models import User, UserStatus
from app.user.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    PaginationParams,
)

if TYPE_CHECKING:
    from app.notification.services import NotificationService

logger = get_logger(__name__)


class UserService:
    """
    사용자 서비스

    사용자 생성, 조회, 수정, 삭제 등의 비즈니스 로직을 처리합니다.

    Attributes:
        session: 비동기 데이터베이스 세션
        notification_service: 알림 서비스 (선택적)
    """

    def __init__(
        self,
        session: AsyncSession,
        notification_service: NotificationService | None = None,
    ):
        self.session = session
        self.notification_service = notification_service

    # ==================== 조회 메서드 ====================

    async def get_by_id(self, user_id: int) -> User:
        """
        ID로 사용자를 조회합니다.

        Args:
            user_id: 사용자 ID

        Returns:
            조회된 User 엔티티

        Raises:
            NotFoundError: 사용자가 존재하지 않는 경우
        """
        logger.debug(f"사용자 조회", extra={"user_id": user_id})

        stmt = select(User).where(
            User.id == user_id,
            User.is_deleted == False  # noqa: E712
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"사용자 없음", extra={"user_id": user_id})
            raise NotFoundError(
                message="사용자를 찾을 수 없습니다",
                detail={"user_id": user_id}
            )

        return user

    async def get_by_email(self, email: str) -> User | None:
        """
        이메일로 사용자를 조회합니다.

        Args:
            email: 사용자 이메일

        Returns:
            User 또는 None
        """
        stmt = select(User).where(
            User.email == email,
            User.is_deleted == False  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_list(
        self,
        params: PaginationParams,
        status: UserStatus | None = None,
        search: str | None = None,
    ) -> UserListResponse:
        """
        사용자 목록을 페이지네이션하여 조회합니다.

        Args:
            params: 페이지네이션 파라미터
            status: 상태 필터 (선택적)
            search: 검색어 (선택적)

        Returns:
            페이지네이션된 사용자 목록
        """
        logger.debug(
            f"사용자 목록 조회",
            extra={"page": params.page, "size": params.size, "status": status}
        )

        # 기본 쿼리
        base_query = select(User).where(User.is_deleted == False)  # noqa: E712

        # 필터 적용
        if status:
            base_query = base_query.where(User.status == status)
        if search:
            search_pattern = f"%{search}%"
            base_query = base_query.where(
                (User.name.ilike(search_pattern)) |
                (User.email.ilike(search_pattern))
            )

        # 전체 카운트 (병렬 실행)
        count_query = select(func.count()).select_from(base_query.subquery())

        # 정렬 및 페이지네이션
        items_query = (
            base_query
            .order_by(User.created_at.desc())
            .offset((params.page - 1) * params.size)
            .limit(params.size)
        )

        # 병렬 실행
        count_result, items_result = await asyncio.gather(
            self.session.execute(count_query),
            self.session.execute(items_query),
        )

        total_items = count_result.scalar() or 0
        items = list(items_result.scalars().all())

        return UserListResponse.from_query_result(
            items=items,
            total_items=total_items,
            page=params.page,
            size=params.size,
        )

    # ==================== 생성/수정 메서드 ====================

    async def create(self, data: UserCreate) -> User:
        """
        새로운 사용자를 생성합니다.

        Args:
            data: 사용자 생성 데이터

        Returns:
            생성된 User 엔티티

        Raises:
            ConflictError: 이메일이 이미 존재하는 경우
            ValidationError: 비밀번호 정책 위반
        """
        logger.info(f"사용자 생성 시작", extra={"email": data.email})

        # 1. 이메일 중복 체크
        existing = await self.get_by_email(data.email)
        if existing:
            logger.warning(f"이메일 중복", extra={"email": data.email})
            raise ConflictError(
                message="이미 등록된 이메일입니다",
                detail={"email": data.email}
            )

        # 2. 비밀번호 정책 검증
        self._validate_password(data.password)

        # 3. 사용자 생성
        user = User(
            email=data.email,
            password_hash=get_password_hash(data.password),
            name=data.name,
            phone=data.phone,
            status=UserStatus.PENDING,
        )
        self.session.add(user)
        await self.session.flush()  # ID 생성

        logger.info(f"사용자 생성 완료", extra={"user_id": user.id})

        # 4. 환영 이메일 발송 (비동기, 실패해도 롤백하지 않음)
        if self.notification_service:
            asyncio.create_task(
                self._send_welcome_email(user)
            )

        return user

    async def update(self, user_id: int, data: UserUpdate) -> User:
        """
        사용자 정보를 수정합니다.

        Args:
            user_id: 사용자 ID
            data: 수정할 데이터

        Returns:
            수정된 User 엔티티

        Raises:
            NotFoundError: 사용자가 존재하지 않는 경우
            ConflictError: 변경하려는 이메일이 이미 존재하는 경우
        """
        logger.info(f"사용자 수정", extra={"user_id": user_id})

        user = await self.get_by_id(user_id)

        # 이메일 변경 시 중복 체크
        if data.email and data.email != user.email:
            existing = await self.get_by_email(data.email)
            if existing:
                raise ConflictError(
                    message="이미 등록된 이메일입니다",
                    detail={"email": data.email}
                )

        # 업데이트 (None이 아닌 값만)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        await self.session.flush()
        logger.info(f"사용자 수정 완료", extra={"user_id": user_id})

        return user

    async def delete(self, user_id: int) -> None:
        """
        사용자를 소프트 삭제합니다.

        Args:
            user_id: 사용자 ID

        Raises:
            NotFoundError: 사용자가 존재하지 않는 경우
        """
        logger.info(f"사용자 삭제", extra={"user_id": user_id})

        user = await self.get_by_id(user_id)
        user.soft_delete()

        await self.session.flush()
        logger.info(f"사용자 삭제 완료", extra={"user_id": user_id})

    # ==================== 인증 관련 메서드 ====================

    async def authenticate(self, email: str, password: str) -> User:
        """
        이메일과 비밀번호로 사용자를 인증합니다.

        Args:
            email: 사용자 이메일
            password: 비밀번호

        Returns:
            인증된 User 엔티티

        Raises:
            ValidationError: 인증 실패
        """
        user = await self.get_by_email(email)

        if not user or not verify_password(password, user.password_hash):
            logger.warning(f"인증 실패", extra={"email": email})
            raise ValidationError(message="이메일 또는 비밀번호가 올바르지 않습니다")

        if user.status != UserStatus.ACTIVE:
            logger.warning(f"비활성 계정 로그인 시도", extra={"email": email})
            raise ValidationError(message="활성화되지 않은 계정입니다")

        logger.info(f"인증 성공", extra={"user_id": user.id})
        return user

    async def activate(self, user_id: int) -> User:
        """
        사용자 계정을 활성화합니다.

        Args:
            user_id: 사용자 ID

        Returns:
            활성화된 User 엔티티
        """
        user = await self.get_by_id(user_id)

        if user.status == UserStatus.ACTIVE:
            logger.info(f"이미 활성화된 계정", extra={"user_id": user_id})
            return user

        user.status = UserStatus.ACTIVE
        await self.session.flush()

        logger.info(f"계정 활성화 완료", extra={"user_id": user_id})
        return user

    # ==================== Private 메서드 ====================

    def _validate_password(self, password: str) -> None:
        """비밀번호 정책 검증"""
        errors = []

        if len(password) < 8:
            errors.append("비밀번호는 8자 이상이어야 합니다")
        if not any(c.isupper() for c in password):
            errors.append("대문자를 포함해야 합니다")
        if not any(c.islower() for c in password):
            errors.append("소문자를 포함해야 합니다")
        if not any(c.isdigit() for c in password):
            errors.append("숫자를 포함해야 합니다")

        if errors:
            raise ValidationError(
                message="비밀번호 정책을 충족하지 않습니다",
                detail={"errors": errors}
            )

    async def _send_welcome_email(self, user: User) -> None:
        """환영 이메일 발송 (실패해도 로그만 남김)"""
        try:
            if self.notification_service:
                await self.notification_service.send_welcome_email(user.email)
                logger.info(f"환영 이메일 발송 완료", extra={"user_id": user.id})
        except Exception as e:
            logger.error(
                f"환영 이메일 발송 실패",
                extra={"user_id": user.id, "error": str(e)}
            )
```

## 의존성 주입

```python
# app/user/dependencies.py
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.user.services.user import UserService
from app.notification.dependencies import get_notification_service
from app.notification.services import NotificationService


async def get_user_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    notification_service: Annotated[
        NotificationService | None,
        Depends(get_notification_service)
    ] = None,
) -> UserService:
    """UserService 의존성 주입"""
    return UserService(
        session=session,
        notification_service=notification_service,
    )
```
