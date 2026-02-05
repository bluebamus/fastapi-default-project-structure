# UnitOfWork 패턴 설계 가이드

본 문서는 FastAPI 애플리케이션에서 UnitOfWork 패턴을 구현하는 두 가지 접근 방식에 대해 기술한다. 각 방식의 설계 철학, 구현 방법, 실행 흐름을 상세히 다루며, 실무 프로젝트에서의 적용 사례를 포함한다.

---

## 목차

1. [개요](#1-개요)
2. [옵션 2: 도메인별 UnitOfWork 패턴](#2-옵션-2-도메인별-unitofwork-패턴)
3. [옵션 3: Generic UnitOfWork 패턴](#3-옵션-3-generic-unitofwork-패턴)
4. [두 패턴의 비교 분석](#4-두-패턴의-비교-분석)
5. [실무 프로젝트 시나리오](#5-실무-프로젝트-시나리오)
6. [결론 및 권장사항](#6-결론-및-권장사항)

---

## 1. 개요

### 1.1 UnitOfWork 패턴의 정의

UnitOfWork 패턴은 Martin Fowler가 정의한 엔터프라이즈 애플리케이션 아키텍처 패턴 중 하나이다. 이 패턴의 핵심 목적은 비즈니스 트랜잭션 동안 수행된 모든 변경 사항을 추적하고, 트랜잭션이 완료될 때 이를 일괄적으로 데이터베이스에 반영하는 것이다.

UnitOfWork는 다음과 같은 책임을 가진다.

첫째, 트랜잭션 경계를 정의하고 관리한다. 하나의 비즈니스 작업이 시작되고 완료될 때까지의 범위를 명확히 하며, 이 범위 내에서 발생하는 모든 데이터베이스 작업이 원자적으로 처리되도록 보장한다.

둘째, 여러 Repository를 통합하여 단일 진입점을 제공한다. 서비스 계층에서 여러 Repository에 접근해야 할 때, UnitOfWork를 통해 일관된 방식으로 접근할 수 있다.

셋째, 세션 생명주기를 관리한다. 데이터베이스 세션의 생성, 사용, 해제를 캡슐화하여 자원 누수를 방지한다.

### 1.2 패턴 선택의 중요성

UnitOfWork를 구현하는 방식은 애플리케이션의 확장성, 유지보수성, 테스트 용이성에 직접적인 영향을 미친다. 잘못된 설계는 도메인 간 결합도를 높이고, 코드 변경 시 예상치 못한 부작용을 야기할 수 있다. 따라서 프로젝트의 특성과 팀의 역량을 고려하여 적절한 패턴을 선택해야 한다.

---

## 2. 옵션 2: 도메인별 UnitOfWork 패턴

### 2.1 설계 철학

도메인별 UnitOfWork 패턴은 도메인 주도 설계(Domain-Driven Design)의 Bounded Context 개념을 UnitOfWork 수준에서 적용한 것이다. 각 비즈니스 도메인은 자신만의 UnitOfWork 클래스를 가지며, 해당 도메인에서 필요한 Repository만을 포함한다.

이 접근 방식의 핵심 원칙은 다음과 같다.

첫째, 도메인 독립성이다. 각 도메인은 다른 도메인의 내부 구조를 알 필요가 없다. Home 도메인의 UnitOfWork는 User 도메인의 Repository 존재 여부를 인식하지 않는다.

둘째, 명시적 의존성이다. UnitOfWork 클래스의 정의만 보면 해당 도메인에서 어떤 Repository를 사용하는지 즉시 파악할 수 있다. 이는 코드의 가독성과 유지보수성을 높인다.

셋째, 타입 안전성이다. 각 UnitOfWork 클래스에 Repository가 명시적으로 선언되므로, IDE의 자동완성과 정적 타입 검사 도구의 지원을 완전히 받을 수 있다.

### 2.2 디렉토리 구조

도메인별 UnitOfWork 패턴을 적용한 프로젝트의 디렉토리 구조는 다음과 같다.

```
app/
├── database/
│   ├── __init__.py
│   ├── session.py                    # 세션 팩토리 및 엔진 설정
│   ├── unit_of_work.py               # BaseUnitOfWork 정의
│   └── repositories/
│       ├── __init__.py
│       └── base.py                   # BaseRepository 정의
│
├── home/
│   ├── __init__.py
│   ├── unit_of_work.py               # HomeUnitOfWork 정의
│   ├── models/
│   │   └── models.py
│   ├── repositories/
│   │   └── user_access_log_repository.py
│   ├── services/
│   │   └── user_access_log_service.py
│   └── api/
│       └── routers/
│           └── v1/
│               └── home.py
│
├── user/
│   ├── __init__.py
│   ├── unit_of_work.py               # UserUnitOfWork 정의
│   ├── models/
│   │   └── models.py
│   ├── repositories/
│   │   ├── user_repository.py
│   │   └── user_profile_repository.py
│   ├── services/
│   │   └── user_service.py
│   └── api/
│       └── routers/
│           └── v1/
│               └── user.py
│
└── blog/
    ├── __init__.py
    ├── unit_of_work.py               # BlogUnitOfWork 정의
    ├── models/
    │   └── models.py
    ├── repositories/
    │   ├── post_repository.py
    │   └── comment_repository.py
    ├── services/
    │   └── blog_service.py
    └── api/
        └── routers/
            └── v1/
                └── blog.py
```

### 2.3 구현 코드

#### 2.3.1 BaseUnitOfWork (공통 기반 클래스)

```python
# app/database/unit_of_work.py
"""
UnitOfWork 패턴의 기반 클래스를 정의한다.

이 모듈은 모든 도메인별 UnitOfWork가 상속받는 추상 기반 클래스를 제공한다.
BaseUnitOfWork는 세션 관리와 트랜잭션 제어만을 담당하며,
구체적인 Repository 정의는 하위 클래스에 위임한다.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, BackgroundSessionLocal
from app.utils.logger import get_logger

logger = get_logger("unit_of_work")


class BaseUnitOfWork:
    """
    UnitOfWork 패턴의 기반 클래스.

    이 클래스는 데이터베이스 세션의 생명주기와 트랜잭션 경계를 관리한다.
    Repository는 포함하지 않으며, 각 도메인별 하위 클래스에서 정의한다.

    이 클래스는 Python의 비동기 컨텍스트 매니저 프로토콜을 구현하여
    async with 구문과 함께 사용할 수 있다.

    Attributes:
        _session: 데이터베이스 세션 인스턴스
        _owns_session: 세션 소유권 여부 (True면 이 인스턴스가 세션을 생성함)

    Example:
        이 클래스는 직접 사용하지 않고, 하위 클래스를 통해 사용한다.

        class HomeUnitOfWork(BaseUnitOfWork):
            user_access_logs: UserAccessLogRepository

            async def __aenter__(self) -> Self:
                await super().__aenter__()
                self.user_access_logs = UserAccessLogRepository(self._session)
                return self
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        """
        BaseUnitOfWork를 초기화한다.

        외부에서 세션을 주입받을 수 있으며, 주입받지 않은 경우
        컨텍스트 진입 시 자동으로 새 세션을 생성한다.

        Args:
            session: 외부에서 주입할 세션. None인 경우 자동 생성한다.
        """
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Self:
        """
        비동기 컨텍스트 매니저 진입점.

        세션이 주입되지 않은 경우 새 세션을 생성한다.
        하위 클래스에서는 이 메서드를 오버라이드하여 Repository를 초기화한다.

        Returns:
            Self: UnitOfWork 인스턴스 자신
        """
        if self._owns_session:
            self._session = AsyncSessionLocal()

        logger.debug("[BaseUnitOfWork] 컨텍스트 진입")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        비동기 컨텍스트 매니저 종료점.

        예외가 발생한 경우 자동으로 롤백을 수행한다.
        세션을 직접 생성한 경우(소유권이 있는 경우) 세션을 닫는다.

        Args:
            exc_type: 발생한 예외의 타입 (없으면 None)
            exc_val: 발생한 예외 인스턴스 (없으면 None)
            exc_tb: 예외의 트레이스백 (없으면 None)
        """
        if exc_type is not None:
            logger.error(
                f"[BaseUnitOfWork] 예외 발생으로 롤백 수행: "
                f"{exc_type.__name__}: {exc_val}"
            )
            await self.rollback()

        if self._owns_session and self._session:
            await self._session.close()
            logger.debug("[BaseUnitOfWork] 세션 종료")

    @property
    def session(self) -> AsyncSession:
        """
        현재 세션을 반환한다.

        Returns:
            AsyncSession: 현재 활성화된 데이터베이스 세션

        Raises:
            RuntimeError: UnitOfWork가 컨텍스트에 진입하지 않은 경우
        """
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork가 시작되지 않았습니다. "
                "async with 구문 내에서 사용하세요."
            )
        return self._session

    async def commit(self) -> None:
        """
        현재 트랜잭션을 커밋한다.

        모든 변경 사항을 데이터베이스에 영구적으로 반영한다.
        커밋 후에는 새로운 트랜잭션이 자동으로 시작된다.
        """
        logger.debug("[BaseUnitOfWork] 커밋 수행")
        await self.session.commit()

    async def rollback(self) -> None:
        """
        현재 트랜잭션을 롤백한다.

        현재 트랜잭션에서 수행된 모든 변경 사항을 취소한다.
        """
        logger.debug("[BaseUnitOfWork] 롤백 수행")
        await self.session.rollback()

    async def flush(self) -> None:
        """
        세션의 변경 사항을 데이터베이스에 전송한다.

        flush는 변경 사항을 데이터베이스에 전송하지만 커밋하지는 않는다.
        이를 통해 데이터베이스에서 생성된 값(예: auto increment ID)을
        트랜잭션 커밋 전에 조회할 수 있다.
        """
        await self.session.flush()


class BaseBackgroundUnitOfWork(BaseUnitOfWork):
    """
    백그라운드 태스크용 UnitOfWork 기반 클래스.

    메인 API 요청과 분리된 커넥션 풀을 사용하여
    백그라운드 작업이 API 응답 성능에 영향을 주지 않도록 한다.

    주요 사용 사례:
        - 접속 로그 비동기 저장
        - 이메일 발송 기록
        - 통계 데이터 집계
        - 배치 작업
    """

    async def __aenter__(self) -> Self:
        """
        백그라운드 세션을 사용하여 컨텍스트에 진입한다.
        """
        if self._owns_session:
            self._session = BackgroundSessionLocal()

        logger.debug("[BaseBackgroundUnitOfWork] 컨텍스트 진입")
        return self
```

#### 2.3.2 도메인별 UnitOfWork 구현

```python
# app/home/unit_of_work.py
"""
Home 도메인 전용 UnitOfWork 구현.

이 모듈은 Home 도메인에서 사용하는 UnitOfWork 클래스를 정의한다.
Home 도메인은 사용자 접속 로그와 관련된 기능을 담당한다.
"""

from typing import Self

from app.database.unit_of_work import BaseUnitOfWork, BaseBackgroundUnitOfWork
from app.home.repositories.user_access_log_repository import UserAccessLogRepository
from app.utils.logger import get_logger

logger = get_logger("home_uow")


class HomeUnitOfWork(BaseUnitOfWork):
    """
    Home 도메인 전용 UnitOfWork.

    접속 로그 관련 Repository를 포함하며, Home 도메인의 모든 API 엔드포인트에서
    이 UnitOfWork를 사용하여 데이터에 접근한다.

    Attributes:
        user_access_logs: 사용자 접속 로그 Repository

    Example:
        async with HomeUnitOfWork(session) as uow:
            logs = await uow.user_access_logs.get_recent_logs(limit=50)
            await uow.commit()
    """

    user_access_logs: UserAccessLogRepository

    async def __aenter__(self) -> Self:
        """
        컨텍스트 진입 시 Home 도메인의 Repository를 초기화한다.
        """
        await super().__aenter__()
        self.user_access_logs = UserAccessLogRepository(self._session)
        logger.debug("[HomeUnitOfWork] Repository 초기화 완료")
        return self


class HomeBackgroundUnitOfWork(BaseBackgroundUnitOfWork):
    """
    Home 도메인의 백그라운드 작업용 UnitOfWork.

    미들웨어에서 접속 로그를 비동기적으로 저장할 때 사용한다.
    메인 API 커넥션 풀과 분리되어 있어 API 응답 지연을 방지한다.
    """

    user_access_logs: UserAccessLogRepository

    async def __aenter__(self) -> Self:
        """
        백그라운드 세션으로 컨텍스트에 진입하고 Repository를 초기화한다.
        """
        await super().__aenter__()
        self.user_access_logs = UserAccessLogRepository(self._session)
        logger.debug("[HomeBackgroundUnitOfWork] Repository 초기화 완료")
        return self
```

```python
# app/user/unit_of_work.py
"""
User 도메인 전용 UnitOfWork 구현.

이 모듈은 User 도메인에서 사용하는 UnitOfWork 클래스를 정의한다.
User 도메인은 사용자 계정, 프로필, 인증과 관련된 기능을 담당한다.
"""

from typing import Self

from app.database.unit_of_work import BaseUnitOfWork
from app.user.repositories.user_repository import UserRepository
from app.user.repositories.user_profile_repository import UserProfileRepository
from app.utils.logger import get_logger

logger = get_logger("user_uow")


class UserUnitOfWork(BaseUnitOfWork):
    """
    User 도메인 전용 UnitOfWork.

    사용자 계정 및 프로필 관련 Repository를 포함한다.
    사용자 CRUD 작업과 프로필 관리 기능에서 사용된다.

    Attributes:
        users: 사용자 계정 Repository
        profiles: 사용자 프로필 Repository

    Example:
        async with UserUnitOfWork(session) as uow:
            user = await uow.users.create({"email": "user@example.com"})
            await uow.profiles.create({"user_id": user.id, "nickname": "John"})
            await uow.commit()
    """

    users: UserRepository
    profiles: UserProfileRepository

    async def __aenter__(self) -> Self:
        """
        컨텍스트 진입 시 User 도메인의 Repository를 초기화한다.
        """
        await super().__aenter__()
        self.users = UserRepository(self._session)
        self.profiles = UserProfileRepository(self._session)
        logger.debug("[UserUnitOfWork] Repository 초기화 완료")
        return self
```

```python
# app/blog/unit_of_work.py
"""
Blog 도메인 전용 UnitOfWork 구현.

이 모듈은 Blog 도메인에서 사용하는 UnitOfWork 클래스를 정의한다.
Blog 도메인은 게시글, 댓글, 카테고리와 관련된 기능을 담당한다.
"""

from typing import Self

from app.database.unit_of_work import BaseUnitOfWork
from app.blog.repositories.post_repository import PostRepository
from app.blog.repositories.comment_repository import CommentRepository
from app.blog.repositories.category_repository import CategoryRepository
from app.utils.logger import get_logger

logger = get_logger("blog_uow")


class BlogUnitOfWork(BaseUnitOfWork):
    """
    Blog 도메인 전용 UnitOfWork.

    게시글, 댓글, 카테고리 관련 Repository를 포함한다.
    블로그 기능의 모든 데이터 접근에서 사용된다.

    Attributes:
        posts: 게시글 Repository
        comments: 댓글 Repository
        categories: 카테고리 Repository

    Example:
        async with BlogUnitOfWork(session) as uow:
            post = await uow.posts.create({
                "title": "새 글",
                "content": "내용",
                "author_id": user_id
            })
            await uow.commit()
    """

    posts: PostRepository
    comments: CommentRepository
    categories: CategoryRepository

    async def __aenter__(self) -> Self:
        """
        컨텍스트 진입 시 Blog 도메인의 Repository를 초기화한다.
        """
        await super().__aenter__()
        self.posts = PostRepository(self._session)
        self.comments = CommentRepository(self._session)
        self.categories = CategoryRepository(self._session)
        logger.debug("[BlogUnitOfWork] Repository 초기화 완료")
        return self
```

### 2.4 실행 흐름

도메인별 UnitOfWork 패턴의 실행 흐름을 단계별로 설명한다.

#### 2.4.1 API 요청 처리 흐름

```
[1] 클라이언트 요청
     |
     v
[2] FastAPI 라우터
     |
     +-- Depends(get_session) 호출
     |   |
     |   v
     |   [3] get_session() 제너레이터 실행
     |       - AsyncSessionLocal()로 세션 생성
     |       - yield session
     |
     v
[4] 라우터 핸들러 함수 진입
     |
     +-- async with HomeUnitOfWork(session) as uow:
     |   |
     |   v
     |   [5] HomeUnitOfWork.__aenter__() 호출
     |       - 부모 클래스의 __aenter__() 호출
     |       - self._session에 주입받은 세션 저장
     |       - UserAccessLogRepository(self._session) 인스턴스 생성
     |       - self.user_access_logs에 할당
     |       - self 반환
     |
     v
[6] 비즈니스 로직 실행
     |
     +-- Service 생성: UserAccessLogService(uow.user_access_logs)
     |
     +-- Service 메서드 호출
     |   |
     |   v
     |   [7] Repository 메서드 호출
     |       - uow.user_access_logs.get_recent_logs()
     |       - SQL 쿼리 실행
     |       - 결과 반환
     |
     +-- uow.commit() 호출 (필요한 경우)
     |   |
     |   v
     |   [8] 트랜잭션 커밋
     |       - session.commit() 실행
     |       - 변경 사항 데이터베이스 반영
     |
     v
[9] async with 블록 종료
     |
     +-- HomeUnitOfWork.__aexit__() 호출
     |   - 예외 발생 시 rollback() 수행
     |   - 세션 소유권이 없으므로 세션 닫지 않음
     |
     v
[10] 라우터 핸들러 함수 종료
     |
     +-- get_session() 제너레이터 재개
     |   - yield 이후 코드 실행
     |   - finally 블록에서 세션 정리
     |
     v
[11] 응답 반환
```

#### 2.4.2 의존성 방향

```
app/database/                      app/home/
+---------------------------+      +---------------------------+
|                           |      |                           |
|  BaseUnitOfWork           |<-----|  HomeUnitOfWork           |
|  (세션 관리만 담당)       |      |  (Repository 포함)        |
|                           |      |                           |
|  BaseRepository           |<-----|  UserAccessLogRepository  |
|  (CRUD 기본 로직)         |      |  (도메인 특화 로직)       |
|                           |      |                           |
+---------------------------+      +---------------------------+

의존 방향: 도메인 -> 인프라스트럭처 (올바른 방향)
```

---

## 3. 옵션 3: Generic UnitOfWork 패턴

### 3.1 설계 철학

Generic UnitOfWork 패턴은 의존성 주입(Dependency Injection) 원칙을 UnitOfWork 수준에서 적용한 것이다. UnitOfWork 클래스 자체는 어떤 구체적인 Repository도 알지 못하며, 사용 시점에 필요한 Repository들을 외부에서 주입받는다.

이 접근 방식의 핵심 원칙은 다음과 같다.

첫째, 설정을 통한 유연성이다. 동일한 UnitOfWork 클래스가 상황에 따라 다른 Repository 조합을 가질 수 있다. 이는 Spring Framework의 DI 컨테이너나 .NET의 서비스 컨테이너와 유사한 개념이다.

둘째, 단일 클래스 원칙이다. 도메인 수에 관계없이 UnitOfWork 클래스는 하나만 존재한다. 이를 통해 코드 중복을 제거하고 관리 포인트를 줄인다.

셋째, 런타임 구성이다. Repository 조합이 컴파일 타임이 아닌 런타임에 결정되므로, 동적인 요구사항에 대응하기 용이하다.

### 3.2 디렉토리 구조

Generic UnitOfWork 패턴을 적용한 프로젝트의 디렉토리 구조는 다음과 같다.

```
app/
├── database/
│   ├── __init__.py
│   ├── session.py                    # 세션 팩토리 및 엔진 설정
│   ├── unit_of_work.py               # GenericUnitOfWork 정의 (단일 클래스)
│   └── repositories/
│       ├── __init__.py
│       └── base.py                   # BaseRepository 정의
│
├── home/
│   ├── __init__.py
│   ├── models/
│   │   └── models.py
│   ├── repositories/
│   │   └── user_access_log_repository.py
│   ├── services/
│   │   └── user_access_log_service.py
│   └── api/
│       └── routers/
│           └── v1/
│               └── home.py           # UnitOfWork에 Repository 주입
│
├── user/
│   ├── __init__.py
│   ├── models/
│   │   └── models.py
│   ├── repositories/
│   │   ├── user_repository.py
│   │   └── user_profile_repository.py
│   ├── services/
│   │   └── user_service.py
│   └── api/
│       └── routers/
│           └── v1/
│               └── user.py           # UnitOfWork에 Repository 주입
│
└── blog/
    ├── __init__.py
    ├── models/
    │   └── models.py
    ├── repositories/
    │   ├── post_repository.py
    │   └── comment_repository.py
    ├── services/
    │   └── blog_service.py
    └── api/
        └── routers/
            └── v1/
                └── blog.py           # UnitOfWork에 Repository 주입
```

### 3.3 구현 코드

#### 3.3.1 GenericUnitOfWork 구현

```python
# app/database/unit_of_work.py
"""
Generic UnitOfWork 패턴 구현.

이 모듈은 Repository를 동적으로 주입받는 범용 UnitOfWork 클래스를 제공한다.
어떤 Repository를 사용할지는 인스턴스 생성 시점에 딕셔너리로 전달한다.
"""

from types import TracebackType
from typing import Any, Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, BackgroundSessionLocal
from app.database.repositories.base import BaseRepository
from app.utils.logger import get_logger

logger = get_logger("unit_of_work")


class UnitOfWork:
    """
    범용 UnitOfWork 클래스.

    Repository를 생성 시점에 동적으로 주입받아 사용한다.
    이를 통해 단일 클래스로 모든 도메인의 데이터 접근을 처리할 수 있다.

    이 방식의 핵심 개념은 "설정을 통한 구성(Configuration over Convention)"이다.
    UnitOfWork 인스턴스를 생성할 때 repositories 딕셔너리를 전달하면,
    해당 딕셔너리의 키가 인스턴스의 속성 이름이 되고 값은 Repository 인스턴스가 된다.

    Attributes:
        _session: 데이터베이스 세션 인스턴스
        _owns_session: 세션 소유권 여부
        _repo_classes: 주입받은 Repository 클래스들의 딕셔너리
        _repositories: 인스턴스화된 Repository들의 딕셔너리

    Example:
        async with UnitOfWork(
            session=session,
            repositories={
                "users": UserRepository,
                "profiles": UserProfileRepository,
            }
        ) as uow:
            user = await uow.users.get_by_id(user_id)
            profile = await uow.profiles.get_by_user_id(user_id)

    Note:
        이 패턴은 유연성을 제공하지만, 타입 안전성이 약화된다는 점을 인지해야 한다.
        IDE의 자동완성이 제한적으로 작동하며, 잘못된 속성 접근은 런타임에야 발견된다.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        repositories: dict[str, type[BaseRepository]] | None = None,
    ) -> None:
        """
        UnitOfWork를 초기화한다.

        Args:
            session: 외부에서 주입할 세션. None인 경우 자동 생성한다.
            repositories: 사용할 Repository 클래스들의 딕셔너리.
                         키는 접근할 때 사용할 속성 이름이고,
                         값은 Repository 클래스(타입)이다.

        Example:
            UnitOfWork(repositories={
                "users": UserRepository,      # uow.users로 접근
                "posts": PostRepository,      # uow.posts로 접근
            })
        """
        self._session = session
        self._owns_session = session is None
        self._repo_classes = repositories or {}
        self._repositories: dict[str, BaseRepository] = {}

    async def __aenter__(self) -> Self:
        """
        비동기 컨텍스트 매니저 진입점.

        세션을 생성(또는 주입받은 세션 사용)하고,
        전달받은 Repository 클래스들을 인스턴스화하여 속성으로 추가한다.

        Returns:
            Self: UnitOfWork 인스턴스 자신
        """
        if self._owns_session:
            self._session = AsyncSessionLocal()

        # 전달받은 Repository 클래스들을 인스턴스화
        for name, repo_class in self._repo_classes.items():
            repo_instance = repo_class(self._session)
            self._repositories[name] = repo_instance
            # 동적으로 속성 추가하여 uow.users, uow.posts 형태로 접근 가능하게 함
            setattr(self, name, repo_instance)

        logger.debug(
            f"[UnitOfWork] 컨텍스트 진입, "
            f"등록된 Repository: {list(self._repositories.keys())}"
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        비동기 컨텍스트 매니저 종료점.

        예외 발생 시 롤백을 수행하고, 세션 소유권이 있으면 세션을 닫는다.
        """
        if exc_type is not None:
            logger.error(
                f"[UnitOfWork] 예외 발생으로 롤백: "
                f"{exc_type.__name__}: {exc_val}"
            )
            await self.rollback()

        if self._owns_session and self._session:
            await self._session.close()
            logger.debug("[UnitOfWork] 세션 종료")

    def __getattr__(self, name: str) -> Any:
        """
        등록되지 않은 Repository에 접근 시 명확한 에러 메시지를 제공한다.

        이 메서드는 일반적인 속성 접근이 실패했을 때 호출된다.
        등록된 Repository 목록을 포함한 에러 메시지를 생성하여
        디버깅을 용이하게 한다.

        Args:
            name: 접근하려는 속성 이름

        Returns:
            Any: 이 메서드는 항상 예외를 발생시킨다

        Raises:
            AttributeError: 항상 발생하며, 등록된 Repository 목록을 포함한다
        """
        # 내부 속성(언더스코어로 시작)은 일반적인 AttributeError 발생
        if name.startswith("_"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        # Repository 접근 시도로 간주하고 도움이 되는 에러 메시지 제공
        registered = list(self._repositories.keys()) if self._repositories else []
        raise AttributeError(
            f"'{name}' Repository가 등록되지 않았습니다. "
            f"등록된 Repository: {registered}. "
            f"UnitOfWork 생성 시 repositories 딕셔너리에 추가하세요."
        )

    @property
    def session(self) -> AsyncSession:
        """현재 세션을 반환한다."""
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork가 시작되지 않았습니다. "
                "async with 구문 내에서 사용하세요."
            )
        return self._session

    async def commit(self) -> None:
        """현재 트랜잭션을 커밋한다."""
        logger.debug("[UnitOfWork] 커밋 수행")
        await self.session.commit()

    async def rollback(self) -> None:
        """현재 트랜잭션을 롤백한다."""
        logger.debug("[UnitOfWork] 롤백 수행")
        await self.session.rollback()

    async def flush(self) -> None:
        """세션의 변경 사항을 데이터베이스에 전송한다."""
        await self.session.flush()


class BackgroundUnitOfWork(UnitOfWork):
    """
    백그라운드 태스크용 Generic UnitOfWork.

    메인 API 커넥션 풀과 분리된 백그라운드 풀을 사용한다.
    사용 방법은 UnitOfWork와 동일하다.
    """

    async def __aenter__(self) -> Self:
        """백그라운드 세션을 사용하여 컨텍스트에 진입한다."""
        if self._owns_session:
            self._session = BackgroundSessionLocal()

        for name, repo_class in self._repo_classes.items():
            repo_instance = repo_class(self._session)
            self._repositories[name] = repo_instance
            setattr(self, name, repo_instance)

        logger.debug(
            f"[BackgroundUnitOfWork] 컨텍스트 진입, "
            f"등록된 Repository: {list(self._repositories.keys())}"
        )
        return self
```

#### 3.3.2 타입 안전성 보완을 위한 팩토리 함수

```python
# app/home/dependencies.py
"""
Home 도메인의 의존성 및 팩토리 함수.

이 모듈은 Home 도메인에서 사용하는 UnitOfWork 팩토리 함수를 제공한다.
팩토리 함수를 사용하면 Repository 구성을 중앙에서 관리하면서도
호출 측 코드를 간결하게 유지할 수 있다.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, BackgroundUnitOfWork
from app.home.repositories.user_access_log_repository import UserAccessLogRepository


def create_home_uow(session: AsyncSession | None = None) -> UnitOfWork:
    """
    Home 도메인용 UnitOfWork를 생성한다.

    이 팩토리 함수는 Home 도메인에서 필요한 Repository들이
    미리 구성된 UnitOfWork 인스턴스를 반환한다.

    Args:
        session: 외부에서 주입할 세션. None이면 자동 생성한다.

    Returns:
        UnitOfWork: Home 도메인용으로 구성된 UnitOfWork 인스턴스

    Example:
        async with create_home_uow(session) as uow:
            logs = await uow.user_access_logs.get_recent_logs()
    """
    return UnitOfWork(
        session=session,
        repositories={
            "user_access_logs": UserAccessLogRepository,
        }
    )


def create_home_background_uow() -> BackgroundUnitOfWork:
    """
    Home 도메인의 백그라운드 작업용 UnitOfWork를 생성한다.

    Returns:
        BackgroundUnitOfWork: 백그라운드 풀을 사용하는 UnitOfWork 인스턴스
    """
    return BackgroundUnitOfWork(
        repositories={
            "user_access_logs": UserAccessLogRepository,
        }
    )
```

```python
# app/user/dependencies.py
"""
User 도메인의 의존성 및 팩토리 함수.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.user.repositories.user_repository import UserRepository
from app.user.repositories.user_profile_repository import UserProfileRepository


def create_user_uow(session: AsyncSession | None = None) -> UnitOfWork:
    """
    User 도메인용 UnitOfWork를 생성한다.

    Args:
        session: 외부에서 주입할 세션

    Returns:
        UnitOfWork: User 도메인용으로 구성된 UnitOfWork 인스턴스
    """
    return UnitOfWork(
        session=session,
        repositories={
            "users": UserRepository,
            "profiles": UserProfileRepository,
        }
    )
```

```python
# app/blog/dependencies.py
"""
Blog 도메인의 의존성 및 팩토리 함수.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.blog.repositories.post_repository import PostRepository
from app.blog.repositories.comment_repository import CommentRepository
from app.blog.repositories.category_repository import CategoryRepository


def create_blog_uow(session: AsyncSession | None = None) -> UnitOfWork:
    """
    Blog 도메인용 UnitOfWork를 생성한다.

    Args:
        session: 외부에서 주입할 세션

    Returns:
        UnitOfWork: Blog 도메인용으로 구성된 UnitOfWork 인스턴스
    """
    return UnitOfWork(
        session=session,
        repositories={
            "posts": PostRepository,
            "comments": CommentRepository,
            "categories": CategoryRepository,
        }
    )


def create_blog_minimal_uow(session: AsyncSession | None = None) -> UnitOfWork:
    """
    Blog 도메인의 최소 구성 UnitOfWork를 생성한다.

    게시글만 필요한 API에서 사용하며, 불필요한 Repository 로드를 방지한다.

    Args:
        session: 외부에서 주입할 세션

    Returns:
        UnitOfWork: 게시글 Repository만 포함된 UnitOfWork 인스턴스
    """
    return UnitOfWork(
        session=session,
        repositories={
            "posts": PostRepository,
        }
    )
```

### 3.4 실행 흐름

Generic UnitOfWork 패턴의 실행 흐름을 단계별로 설명한다.

#### 3.4.1 API 요청 처리 흐름

```
[1] 클라이언트 요청
     |
     v
[2] FastAPI 라우터
     |
     +-- Depends(get_session) 호출
     |   |
     |   v
     |   [3] get_session() 제너레이터 실행
     |       - AsyncSessionLocal()로 세션 생성
     |       - yield session
     |
     v
[4] 라우터 핸들러 함수 진입
     |
     +-- async with UnitOfWork(session, repositories={...}) as uow:
     |   |
     |   v
     |   [5] UnitOfWork.__aenter__() 호출
     |       - self._session에 주입받은 세션 저장
     |       - repositories 딕셔너리 순회
     |       - 각 Repository 클래스를 인스턴스화
     |       - setattr()로 동적 속성 추가
     |       - self 반환
     |
     v
[6] 비즈니스 로직 실행
     |
     +-- uow.users (동적으로 추가된 속성 접근)
     |   |
     |   v
     |   [7] __getattribute__()로 속성 반환
     |       - setattr()로 추가된 속성이므로 정상 반환
     |
     +-- Repository 메서드 호출
     |   |
     |   v
     |   [8] SQL 쿼리 실행, 결과 반환
     |
     +-- uow.commit() 호출
     |
     v
[9] async with 블록 종료
     |
     +-- UnitOfWork.__aexit__() 호출
     |
     v
[10] 응답 반환
```

#### 3.4.2 잘못된 Repository 접근 시 흐름

```
[1] uow.nonexistent 접근 시도
     |
     v
[2] __getattribute__() 호출
     - 속성을 찾지 못함
     |
     v
[3] __getattr__() 호출 (fallback)
     - name = "nonexistent"
     - self._repositories = {"users": ..., "posts": ...}
     |
     v
[4] AttributeError 발생
     - "'nonexistent' Repository가 등록되지 않았습니다.
        등록된 Repository: ['users', 'posts'].
        UnitOfWork 생성 시 repositories 딕셔너리에 추가하세요."
```

#### 3.4.3 의존성 방향

```
app/database/                      app/home/
+---------------------------+      +---------------------------+
|                           |      |                           |
|  UnitOfWork               |      |  home.py (라우터)         |
|  (범용, Repository 없음)  |      |    |                      |
|                           |      |    +-- UnitOfWork 생성    |
|  BaseRepository           |      |    |   repositories={     |
|                           |      |    |     "user_access_logs"|
+---------------------------+      |    |   }                  |
            ^                      |    |                      |
            |                      |    v                      |
            |                      |  UserAccessLogRepository  |
            |                      |                           |
            +----------------------+---------------------------+

의존 방향:
  - 라우터 -> UnitOfWork (인프라)
  - 라우터 -> Repository (도메인)
  - Repository -> BaseRepository (인프라)

UnitOfWork는 어떤 도메인도 알지 못함
```

---

## 4. 두 패턴의 비교 분석

### 4.1 타입 안전성

타입 안전성은 컴파일 타임(또는 정적 분석 시점)에 타입 관련 오류를 감지할 수 있는 정도를 의미한다. 이는 IDE의 자동완성 지원, mypy 등 정적 타입 검사 도구의 활용, 리팩토링 시 안전성과 직결된다.

옵션 2(도메인별 UnitOfWork)에서는 각 UnitOfWork 클래스에 Repository가 명시적으로 타입 선언되어 있다. 따라서 IDE는 uow.user_access_logs가 UserAccessLogRepository 타입임을 알고 있으며, 해당 Repository의 모든 메서드에 대해 자동완성을 제공한다. 존재하지 않는 Repository에 접근하면 IDE에서 즉시 경고가 표시되고, mypy 실행 시 에러로 감지된다.

```python
# 옵션 2에서의 타입 검사
async with HomeUnitOfWork(session) as uow:
    uow.user_access_logs.get_by_ip("192.168.1.1")  # IDE 자동완성 작동
    uow.users.get_by_id("123")  # IDE 에러: HomeUnitOfWork에 users 없음
```

옵션 3(Generic UnitOfWork)에서는 Repository가 런타임에 동적으로 추가되므로, IDE는 uow에 어떤 속성이 있는지 알 수 없다. setattr()로 추가된 속성은 정적 분석 도구가 추적하지 못한다. 따라서 잘못된 Repository 접근은 런타임에야 발견된다.

```python
# 옵션 3에서의 타입 검사
async with UnitOfWork(repositories={"users": UserRepository}) as uow:
    uow.users.get_by_id("123")  # IDE: 'UnitOfWork' has no attribute 'users'
    # 실제로는 작동하지만 IDE가 타입을 모름
```

### 4.2 코드 구조와 관리

옵션 2에서는 도메인 수에 비례하여 UnitOfWork 클래스 파일이 증가한다. 도메인이 10개라면 UnitOfWork 파일도 10개가 된다. 각 파일은 20-40줄 정도의 간단한 보일러플레이트 코드를 포함한다. 이 방식은 각 도메인의 데이터 접근 계층이 어떻게 구성되어 있는지를 명확히 보여주며, 새 팀원이 특정 도메인을 파악할 때 해당 도메인의 UnitOfWork만 확인하면 된다.

옵션 3에서는 UnitOfWork 클래스 파일이 단 하나만 존재한다. 도메인이 아무리 많아도 추가 파일이 필요하지 않다. 대신 각 라우터나 서비스에서 필요한 Repository를 명시적으로 딕셔너리로 전달해야 한다. 이 방식은 파일 수를 최소화하지만, 어떤 도메인에서 어떤 Repository를 사용하는지 파악하려면 실제 사용처를 모두 검색해야 한다.

### 4.3 유연성과 확장성

옵션 2는 정적인 구조를 가진다. 새로운 Repository 조합이 필요하면 새로운 UnitOfWork 클래스를 생성해야 한다. 예를 들어, 블로그 글 작성 시 사용자 통계도 업데이트해야 하는 기능이 추가되면, BlogWithUserStatsUnitOfWork 같은 새 클래스가 필요하다. 이는 클래스 수 증가로 이어지지만, 각 사용 사례가 명확히 문서화되는 효과도 있다.

```python
# 옵션 2: 크로스 도메인 작업을 위한 새 클래스 필요
class BlogWithUserStatsUnitOfWork(BaseUnitOfWork):
    posts: PostRepository
    user_stats: UserStatsRepository

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.posts = PostRepository(self._session)
        self.user_stats = UserStatsRepository(self._session)
        return self
```

옵션 3는 동적인 구조를 가진다. 새로운 Repository 조합이 필요하면 딕셔너리에 항목을 추가하기만 하면 된다. 새 클래스 생성 없이 즉시 사용할 수 있어 빠른 프로토타이핑에 유리하다.

```python
# 옵션 3: 딕셔너리 수정만으로 해결
async with UnitOfWork(
    session=session,
    repositories={
        "posts": PostRepository,
        "user_stats": UserStatsRepository,  # 필요한 것만 추가
    }
) as uow:
    ...
```

### 4.4 테스트 용이성

옵션 2에서 테스트를 위해 Mock을 사용하려면 해당 UnitOfWork 클래스를 상속받아 Mock UnitOfWork를 만들어야 한다.

```python
# 옵션 2: Mock 클래스 필요
class MockHomeUnitOfWork(HomeUnitOfWork):
    async def __aenter__(self) -> Self:
        # 부모 클래스의 세션 생성을 건너뜀
        self.user_access_logs = MockUserAccessLogRepository()
        return self

async def test_get_access_logs():
    async with MockHomeUnitOfWork() as uow:
        result = await some_service_function(uow)
        assert result == expected
```

옵션 3에서는 딕셔너리에 Mock Repository 클래스를 전달하기만 하면 된다. 별도의 Mock UnitOfWork 클래스가 필요하지 않다.

```python
# 옵션 3: 딕셔너리 교체로 간편하게 Mock
async def test_get_access_logs():
    async with UnitOfWork(
        repositories={"user_access_logs": MockUserAccessLogRepository}
    ) as uow:
        result = await some_service_function(uow)
        assert result == expected
```

### 4.5 학습 곡선

옵션 2는 직관적이다. 각 도메인에 해당하는 UnitOfWork 클래스가 있고, 그 안에 Repository가 명시되어 있다. Python의 기본 클래스 상속 개념만 이해하면 패턴을 파악할 수 있다. 새 팀원이 합류했을 때 코드를 이해하는 데 걸리는 시간이 짧다.

옵션 3는 동적 프로그래밍 개념에 대한 이해가 필요하다. setattr()를 통한 동적 속성 추가, __getattr__()를 통한 속성 접근 커스터마이징 등의 메타프로그래밍 기법을 사용한다. 이러한 패턴에 익숙하지 않은 개발자는 코드의 동작 방식을 이해하는 데 시간이 더 걸릴 수 있다.

### 4.6 비교표

| 평가 항목 | 옵션 2 (도메인별) | 옵션 3 (Generic) |
|----------|------------------|------------------|
| 타입 안전성 | 높음 (컴파일 타임 검증) | 낮음 (런타임 검증) |
| IDE 자동완성 | 완벽 지원 | 제한적 지원 |
| 파일 수 | 도메인 수에 비례 증가 | 단일 파일 유지 |
| 유연성 | 낮음 (새 조합 = 새 클래스) | 높음 (딕셔너리 수정) |
| 학습 곡선 | 낮음 (직관적) | 중간 (동적 패턴 이해 필요) |
| 테스트 Mock | Mock 클래스 필요 | 딕셔너리 교체로 간편 |
| 크로스 도메인 | 새 UnitOfWork 클래스 필요 | 딕셔너리에 추가 |
| 도메인 경계 | 명확히 분리 | 사용처에서 결정 |
| 리팩토링 안전성 | 높음 (타입 추적 가능) | 낮음 (동적 속성) |
| 런타임 에러 가능성 | 낮음 | 높음 |
| 코드 명시성 | 높음 (클래스 정의에 명시) | 낮음 (사용처마다 다름) |

---

## 5. 실무 프로젝트 시나리오

본 절에서는 전자상거래(E-Commerce) 플랫폼을 예시로 하여 각 패턴이 실무에서 어떻게 적용되는지 보여준다. 이 플랫폼은 사용자 관리, 상품 카탈로그, 주문 처리, 결제 시스템의 네 가지 주요 도메인을 가진다.

### 5.1 프로젝트 개요

```
ecommerce-platform/
├── app/
│   ├── database/                 # 공통 데이터베이스 인프라
│   ├── user/                     # 사용자 도메인
│   ├── catalog/                  # 상품 카탈로그 도메인
│   ├── order/                    # 주문 도메인
│   └── payment/                  # 결제 도메인
└── tests/
```

### 5.2 옵션 2 적용: 도메인별 UnitOfWork

#### 5.2.1 공통 인프라 계층

```python
# app/database/unit_of_work.py
"""
E-Commerce 플랫폼의 UnitOfWork 기반 클래스.

모든 도메인별 UnitOfWork가 이 클래스를 상속받는다.
세션 관리, 트랜잭션 제어, 로깅 등 공통 기능을 제공한다.
"""

import time
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, BackgroundSessionLocal
from app.core.logging import get_logger
from app.core.metrics import MetricsCollector

logger = get_logger("unit_of_work")
metrics = MetricsCollector()


class BaseUnitOfWork:
    """
    E-Commerce 플랫폼의 UnitOfWork 기반 클래스.

    이 클래스는 다음과 같은 공통 기능을 제공한다.

    1. 세션 생명주기 관리
       - 외부 주입 또는 자동 생성
       - 컨텍스트 종료 시 자동 정리

    2. 트랜잭션 관리
       - commit(), rollback() 메서드
       - 예외 발생 시 자동 롤백

    3. 성능 메트릭 수집
       - 트랜잭션 소요 시간
       - 커밋/롤백 횟수

    Attributes:
        _session: SQLAlchemy 비동기 세션
        _owns_session: 세션 소유권 플래그
        _start_time: 트랜잭션 시작 시간 (메트릭용)
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        """
        기반 UnitOfWork를 초기화한다.

        Args:
            session: 외부에서 주입할 세션.
                    FastAPI의 Depends를 통해 주입받은 세션을 전달한다.
                    None인 경우 __aenter__에서 새 세션을 생성한다.
        """
        self._session = session
        self._owns_session = session is None
        self._start_time: float | None = None

    async def __aenter__(self) -> Self:
        """
        트랜잭션 컨텍스트에 진입한다.

        세션이 없는 경우 새로 생성하고, 트랜잭션 시작 시간을 기록한다.
        하위 클래스는 이 메서드를 오버라이드하여 Repository를 초기화한다.

        Returns:
            Self: UnitOfWork 인스턴스
        """
        self._start_time = time.perf_counter()

        if self._owns_session:
            self._session = AsyncSessionLocal()
            logger.debug("[BaseUnitOfWork] 새 세션 생성")

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        트랜잭션 컨텍스트를 종료한다.

        예외 발생 시 롤백을 수행하고, 성능 메트릭을 기록한다.
        세션 소유권이 있는 경우 세션을 닫는다.
        """
        elapsed = time.perf_counter() - self._start_time if self._start_time else 0

        if exc_type is not None:
            await self.rollback()
            logger.error(
                f"[BaseUnitOfWork] 트랜잭션 실패: {exc_type.__name__}: {exc_val}, "
                f"소요 시간: {elapsed*1000:.2f}ms"
            )
            metrics.increment("uow.rollback.count")
        else:
            metrics.observe("uow.transaction.duration", elapsed)

        if self._owns_session and self._session:
            await self._session.close()
            logger.debug(f"[BaseUnitOfWork] 세션 종료, 소요 시간: {elapsed*1000:.2f}ms")

    @property
    def session(self) -> AsyncSession:
        """현재 활성 세션을 반환한다."""
        if self._session is None:
            raise RuntimeError("UnitOfWork가 시작되지 않았습니다.")
        return self._session

    async def commit(self) -> None:
        """
        현재 트랜잭션을 커밋한다.

        모든 pending 상태의 변경 사항을 데이터베이스에 영구 반영한다.
        커밋 실패 시 자동으로 롤백되지 않으므로, 호출 측에서 예외 처리가 필요하다.
        """
        await self.session.commit()
        metrics.increment("uow.commit.count")
        logger.debug("[BaseUnitOfWork] 트랜잭션 커밋 완료")

    async def rollback(self) -> None:
        """
        현재 트랜잭션을 롤백한다.

        현재 트랜잭션에서 수행된 모든 변경 사항을 취소한다.
        """
        await self.session.rollback()
        logger.debug("[BaseUnitOfWork] 트랜잭션 롤백 완료")

    async def flush(self) -> None:
        """
        세션의 변경 사항을 데이터베이스에 전송한다.

        이 메서드는 변경 사항을 전송만 하고 커밋하지는 않는다.
        주로 auto-increment ID나 default 값을 조회해야 할 때 사용한다.
        """
        await self.session.flush()


class BaseBackgroundUnitOfWork(BaseUnitOfWork):
    """
    백그라운드 작업용 UnitOfWork 기반 클래스.

    API 요청 처리와 분리된 커넥션 풀을 사용하여,
    백그라운드 작업이 API 응답 성능에 영향을 주지 않도록 한다.

    사용 사례:
        - 주문 완료 후 이메일 발송
        - 결제 완료 후 재고 업데이트
        - 비동기 로그 기록
        - 통계 데이터 집계
    """

    async def __aenter__(self) -> Self:
        """백그라운드 전용 커넥션 풀에서 세션을 생성한다."""
        self._start_time = time.perf_counter()

        if self._owns_session:
            self._session = BackgroundSessionLocal()
            logger.debug("[BaseBackgroundUnitOfWork] 백그라운드 세션 생성")

        return self
```

#### 5.2.2 User 도메인

```python
# app/user/unit_of_work.py
"""
User 도메인의 UnitOfWork 구현.

사용자 계정, 프로필, 인증 관련 데이터 접근을 관리한다.
"""

from typing import Self

from app.database.unit_of_work import BaseUnitOfWork
from app.user.repositories.user_repository import UserRepository
from app.user.repositories.user_profile_repository import UserProfileRepository
from app.user.repositories.user_address_repository import UserAddressRepository
from app.core.logging import get_logger

logger = get_logger("user_uow")


class UserUnitOfWork(BaseUnitOfWork):
    """
    User 도메인 전용 UnitOfWork.

    사용자 관리 기능에 필요한 모든 Repository를 포함한다.
    회원가입, 로그인, 프로필 관리, 배송지 관리 등의 기능에서 사용된다.

    Attributes:
        users: 사용자 계정 Repository
               - 이메일, 비밀번호, 계정 상태 관리
               - 로그인 이력, 비밀번호 변경 이력

        profiles: 사용자 프로필 Repository
                  - 닉네임, 프로필 이미지, 자기소개
                  - 마케팅 수신 동의 등 설정

        addresses: 배송지 Repository
                   - 배송지 목록 관리
                   - 기본 배송지 설정

    Example:
        async with UserUnitOfWork(session) as uow:
            # 신규 회원 가입
            user = await uow.users.create({
                "email": "newuser@example.com",
                "password_hash": hashed_password,
                "status": "active"
            })

            # 기본 프로필 생성
            await uow.profiles.create({
                "user_id": user.id,
                "nickname": "새회원",
                "marketing_agreed": False
            })

            await uow.commit()
    """

    # 타입 힌트를 통해 IDE 자동완성과 타입 검사 지원
    users: UserRepository
    profiles: UserProfileRepository
    addresses: UserAddressRepository

    async def __aenter__(self) -> Self:
        """
        컨텍스트 진입 시 User 도메인의 모든 Repository를 초기화한다.

        초기화 순서는 의존성과 무관하게 정의되어 있으나,
        Repository 간 의존성이 있는 경우 순서를 조정해야 할 수 있다.
        """
        await super().__aenter__()

        # 각 Repository에 동일한 세션을 주입하여
        # 모든 작업이 하나의 트랜잭션 내에서 수행되도록 한다
        self.users = UserRepository(self._session)
        self.profiles = UserProfileRepository(self._session)
        self.addresses = UserAddressRepository(self._session)

        logger.debug("[UserUnitOfWork] 초기화 완료: users, profiles, addresses")
        return self
```

```python
# app/user/api/routers/v1/user.py
"""
User API v1 라우터.

사용자 관리 관련 엔드포인트를 정의한다.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.user.unit_of_work import UserUnitOfWork
from app.user.services.user_service import UserService
from app.user.schemas import (
    UserCreateRequest,
    UserResponse,
    UserProfileUpdateRequest,
    AddressCreateRequest,
    AddressResponse,
)
from app.core.logging import get_logger

logger = get_logger("user_router")
router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원 가입",
    description="새로운 사용자 계정을 생성합니다."
)
async def create_user(
    request: UserCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """
    회원 가입 API.

    새로운 사용자 계정과 기본 프로필을 생성한다.
    이메일 중복 확인, 비밀번호 해싱, 프로필 초기화가 모두
    하나의 트랜잭션 내에서 수행된다.

    Args:
        request: 회원 가입 요청 데이터
        session: 데이터베이스 세션 (FastAPI DI)

    Returns:
        생성된 사용자 정보

    Raises:
        HTTPException 409: 이메일 중복
        HTTPException 500: 서버 내부 오류
    """
    logger.info(f"[create_user] 회원 가입 요청: email={request.email}")

    # UserUnitOfWork를 사용하여 User 도메인의 데이터에 접근
    async with UserUnitOfWork(session) as uow:
        # Service 계층에 UnitOfWork의 Repository들을 전달
        service = UserService(
            user_repo=uow.users,
            profile_repo=uow.profiles,
        )

        # 비즈니스 로직 실행
        user = await service.create_user(
            email=request.email,
            password=request.password,
            nickname=request.nickname,
        )

        # 모든 작업이 성공하면 커밋
        await uow.commit()

        logger.info(f"[create_user] 회원 가입 완료: user_id={user.id}")
        return UserResponse.model_validate(user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 조회",
    description="사용자 ID로 사용자 정보를 조회합니다."
)
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """
    사용자 조회 API.

    프로필과 기본 배송지 정보를 함께 조회한다.
    """
    async with UserUnitOfWork(session) as uow:
        # Repository의 Eager Loading 기능을 활용하여
        # N+1 문제 없이 관련 데이터를 조회
        user = await uow.users.get_by_id_with(
            id=user_id,
            relations=["profile", "addresses"],
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"사용자를 찾을 수 없습니다: {user_id}"
            )

        return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="배송지 추가",
)
async def add_address(
    user_id: str,
    request: AddressCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> AddressResponse:
    """
    배송지 추가 API.

    사용자의 배송지 목록에 새 배송지를 추가한다.
    기본 배송지로 설정하는 경우, 기존 기본 배송지 해제도 함께 처리된다.
    """
    async with UserUnitOfWork(session) as uow:
        # 사용자 존재 확인
        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다."
            )

        # 기본 배송지로 설정하는 경우 기존 기본 배송지 해제
        if request.is_default:
            await uow.addresses.update_by(
                data={"is_default": False},
                user_id=user_id,
                is_default=True,
            )

        # 새 배송지 생성
        address = await uow.addresses.create({
            "user_id": user_id,
            "recipient_name": request.recipient_name,
            "phone": request.phone,
            "address_line1": request.address_line1,
            "address_line2": request.address_line2,
            "postal_code": request.postal_code,
            "is_default": request.is_default,
        })

        await uow.commit()
        return AddressResponse.model_validate(address)
```

#### 5.2.3 Order 도메인

```python
# app/order/unit_of_work.py
"""
Order 도메인의 UnitOfWork 구현.

주문 생성, 주문 항목 관리, 주문 상태 추적을 담당한다.
"""

from typing import Self

from app.database.unit_of_work import BaseUnitOfWork, BaseBackgroundUnitOfWork
from app.order.repositories.order_repository import OrderRepository
from app.order.repositories.order_item_repository import OrderItemRepository
from app.order.repositories.order_status_history_repository import (
    OrderStatusHistoryRepository,
)
from app.core.logging import get_logger

logger = get_logger("order_uow")


class OrderUnitOfWork(BaseUnitOfWork):
    """
    Order 도메인 전용 UnitOfWork.

    주문과 관련된 모든 데이터 접근을 관리한다.
    주문 생성 시 주문 정보, 주문 항목, 상태 이력이 모두
    하나의 트랜잭션으로 처리되어야 한다.

    Attributes:
        orders: 주문 메인 테이블 Repository
                - 주문 번호, 주문자 정보, 총액
                - 배송지 정보, 결제 상태

        items: 주문 항목 Repository
               - 주문에 포함된 상품 목록
               - 수량, 단가, 소계

        status_history: 주문 상태 이력 Repository
                        - 주문 상태 변경 추적
                        - 변경 시간, 변경 사유

    Example:
        async with OrderUnitOfWork(session) as uow:
            # 주문 생성
            order = await uow.orders.create({
                "user_id": user_id,
                "total_amount": total,
                "status": "pending"
            })

            # 주문 항목 생성
            for item in cart_items:
                await uow.items.create({
                    "order_id": order.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": item.price,
                })

            # 초기 상태 이력 기록
            await uow.status_history.create({
                "order_id": order.id,
                "status": "pending",
                "note": "주문 접수"
            })

            await uow.commit()
    """

    orders: OrderRepository
    items: OrderItemRepository
    status_history: OrderStatusHistoryRepository

    async def __aenter__(self) -> Self:
        """Order 도메인의 Repository들을 초기화한다."""
        await super().__aenter__()

        self.orders = OrderRepository(self._session)
        self.items = OrderItemRepository(self._session)
        self.status_history = OrderStatusHistoryRepository(self._session)

        logger.debug("[OrderUnitOfWork] 초기화 완료")
        return self


class OrderBackgroundUnitOfWork(BaseBackgroundUnitOfWork):
    """
    Order 도메인의 백그라운드 작업용 UnitOfWork.

    주문 상태 업데이트 이메일 발송, 배송 추적 정보 업데이트 등
    API 응답과 분리되어 비동기로 처리되어야 하는 작업에서 사용한다.
    """

    orders: OrderRepository
    items: OrderItemRepository
    status_history: OrderStatusHistoryRepository

    async def __aenter__(self) -> Self:
        """백그라운드 세션으로 Repository들을 초기화한다."""
        await super().__aenter__()

        self.orders = OrderRepository(self._session)
        self.items = OrderItemRepository(self._session)
        self.status_history = OrderStatusHistoryRepository(self._session)

        logger.debug("[OrderBackgroundUnitOfWork] 초기화 완료")
        return self
```

```python
# app/order/api/routers/v1/order.py
"""
Order API v1 라우터.

주문 생성, 조회, 취소 등의 엔드포인트를 정의한다.
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.order.unit_of_work import OrderUnitOfWork, OrderBackgroundUnitOfWork
from app.order.services.order_service import OrderService
from app.order.schemas import (
    OrderCreateRequest,
    OrderResponse,
    OrderDetailResponse,
    OrderStatusUpdateRequest,
)
from app.core.logging import get_logger
from app.core.events import EventPublisher

logger = get_logger("order_router")
router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="주문 생성",
)
async def create_order(
    request: OrderCreateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    """
    주문 생성 API.

    장바구니의 상품들로 새로운 주문을 생성한다.
    주문 생성 후 이메일 발송 등의 후처리는 백그라운드에서 수행된다.

    처리 흐름:
        1. 장바구니 상품 유효성 검증
        2. 재고 확인
        3. 주문 및 주문 항목 생성
        4. 상태 이력 기록
        5. 커밋
        6. (백그라운드) 주문 확인 이메일 발송
        7. (백그라운드) 재고 차감 이벤트 발행
    """
    logger.info(f"[create_order] 주문 생성 요청: user_id={request.user_id}")

    async with OrderUnitOfWork(session) as uow:
        service = OrderService(
            order_repo=uow.orders,
            item_repo=uow.items,
            history_repo=uow.status_history,
        )

        # 주문 생성 (내부에서 items, history도 함께 생성)
        order = await service.create_order(
            user_id=request.user_id,
            items=request.items,
            shipping_address_id=request.shipping_address_id,
        )

        await uow.commit()

        # 후처리 작업을 백그라운드로 예약
        background_tasks.add_task(
            _send_order_confirmation,
            order_id=order.id,
        )

        logger.info(f"[create_order] 주문 생성 완료: order_id={order.id}")
        return OrderResponse.model_validate(order)


async def _send_order_confirmation(order_id: str) -> None:
    """
    주문 확인 이메일을 발송하는 백그라운드 태스크.

    API 응답과 분리된 커넥션 풀을 사용하여
    이메일 발송 지연이 API 응답에 영향을 주지 않도록 한다.
    """
    async with OrderBackgroundUnitOfWork() as uow:
        order = await uow.orders.get_by_id_with(
            id=order_id,
            relations=["items", "user"],
        )

        if order:
            # 이메일 발송 로직
            await send_email(
                to=order.user.email,
                template="order_confirmation",
                context={"order": order},
            )

            # 이메일 발송 기록
            await uow.status_history.create({
                "order_id": order_id,
                "status": order.status,
                "note": "주문 확인 이메일 발송 완료",
            })

            await uow.commit()


@router.get(
    "/{order_id}",
    response_model=OrderDetailResponse,
    summary="주문 상세 조회",
)
async def get_order(
    order_id: str,
    session: AsyncSession = Depends(get_session),
) -> OrderDetailResponse:
    """
    주문 상세 조회 API.

    주문 정보, 주문 항목, 상태 이력을 모두 포함하여 반환한다.
    """
    async with OrderUnitOfWork(session) as uow:
        order = await uow.orders.get_by_id_with(
            id=order_id,
            relations=["items", "items.product", "status_history"],
        )

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="주문을 찾을 수 없습니다."
            )

        return OrderDetailResponse.model_validate(order)


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    summary="주문 상태 변경",
)
async def update_order_status(
    order_id: str,
    request: OrderStatusUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    """
    주문 상태 변경 API.

    주문 상태를 변경하고 변경 이력을 기록한다.
    상태 전이 규칙에 따라 유효한 변경만 허용된다.
    """
    async with OrderUnitOfWork(session) as uow:
        service = OrderService(
            order_repo=uow.orders,
            item_repo=uow.items,
            history_repo=uow.status_history,
        )

        order = await service.update_status(
            order_id=order_id,
            new_status=request.status,
            note=request.note,
        )

        await uow.commit()
        return OrderResponse.model_validate(order)
```

### 5.3 옵션 3 적용: Generic UnitOfWork

#### 5.3.1 범용 UnitOfWork 클래스

```python
# app/database/unit_of_work.py
"""
E-Commerce 플랫폼의 Generic UnitOfWork 구현.

이 모듈은 Repository를 동적으로 주입받는 범용 UnitOfWork를 제공한다.
모든 도메인에서 단일 클래스를 사용하며, 필요한 Repository는
사용 시점에 딕셔너리로 전달한다.
"""

import time
from types import TracebackType
from typing import Any, Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, BackgroundSessionLocal
from app.database.repositories.base import BaseRepository
from app.core.logging import get_logger
from app.core.metrics import MetricsCollector

logger = get_logger("unit_of_work")
metrics = MetricsCollector()


class UnitOfWork:
    """
    범용 UnitOfWork 클래스.

    Repository를 생성 시점에 딕셔너리로 주입받아 동적으로 구성한다.
    이를 통해 단일 클래스로 모든 도메인의 데이터 접근을 처리할 수 있다.

    동작 원리:
        1. 생성자에서 repositories 딕셔너리를 받는다.
           딕셔너리의 키는 속성 이름, 값은 Repository 클래스이다.

        2. __aenter__에서 각 Repository 클래스를 인스턴스화하고
           setattr()로 self의 속성으로 추가한다.

        3. 사용자는 uow.users, uow.orders 형태로 Repository에 접근한다.

        4. 등록되지 않은 속성에 접근하면 __getattr__에서
           도움이 되는 에러 메시지를 반환한다.

    주의사항:
        이 패턴은 유연성을 제공하지만 타입 안전성이 약화된다.
        IDE 자동완성이 제한적으로 작동하며, 속성 접근 오류는
        런타임에 발견된다. 팩토리 함수와 Protocol을 함께 사용하여
        이 단점을 완화할 수 있다.

    Attributes:
        _session: SQLAlchemy 비동기 세션
        _owns_session: 세션 소유권 플래그
        _repo_classes: 주입받은 Repository 클래스 딕셔너리
        _repositories: 인스턴스화된 Repository 딕셔너리
        _start_time: 트랜잭션 시작 시간 (메트릭용)

    Example:
        async with UnitOfWork(
            session=session,
            repositories={
                "users": UserRepository,
                "orders": OrderRepository,
            }
        ) as uow:
            user = await uow.users.get_by_id(user_id)
            orders = await uow.orders.get_by_user_id(user_id)
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        repositories: dict[str, type[BaseRepository]] | None = None,
    ) -> None:
        """
        UnitOfWork를 초기화한다.

        Args:
            session: 외부에서 주입할 세션.
                    None인 경우 __aenter__에서 자동 생성한다.
            repositories: Repository 클래스 딕셔너리.
                         키: 접근할 때 사용할 속성 이름
                         값: Repository 클래스 (인스턴스가 아닌 타입)

        Example:
            # 직접 사용
            UnitOfWork(repositories={"users": UserRepository})

            # 팩토리 함수 사용 권장
            create_user_uow(session)
        """
        self._session = session
        self._owns_session = session is None
        self._repo_classes = repositories or {}
        self._repositories: dict[str, BaseRepository] = {}
        self._start_time: float | None = None

    async def __aenter__(self) -> Self:
        """
        트랜잭션 컨텍스트에 진입한다.

        세션을 생성(또는 주입받은 세션 사용)하고,
        전달받은 Repository 클래스들을 인스턴스화하여
        self의 속성으로 동적 추가한다.

        Returns:
            Self: UnitOfWork 인스턴스
        """
        self._start_time = time.perf_counter()

        if self._owns_session:
            self._session = AsyncSessionLocal()

        # Repository 클래스들을 인스턴스화하고 속성으로 추가
        for name, repo_class in self._repo_classes.items():
            repo_instance = repo_class(self._session)
            self._repositories[name] = repo_instance
            setattr(self, name, repo_instance)

        repo_names = list(self._repositories.keys())
        logger.debug(f"[UnitOfWork] 진입, repositories={repo_names}")

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        트랜잭션 컨텍스트를 종료한다.
        """
        elapsed = time.perf_counter() - self._start_time if self._start_time else 0

        if exc_type is not None:
            await self.rollback()
            logger.error(
                f"[UnitOfWork] 실패: {exc_type.__name__}: {exc_val}, "
                f"elapsed={elapsed*1000:.2f}ms"
            )
            metrics.increment("uow.rollback.count")
        else:
            metrics.observe("uow.transaction.duration", elapsed)

        if self._owns_session and self._session:
            await self._session.close()

    def __getattr__(self, name: str) -> Any:
        """
        등록되지 않은 Repository 접근 시 명확한 에러 메시지를 제공한다.

        이 메서드는 Python의 속성 조회 프로토콜에 따라,
        __getattribute__에서 속성을 찾지 못했을 때 호출된다.

        Args:
            name: 접근하려는 속성 이름

        Raises:
            AttributeError: 등록된 Repository 목록을 포함한 에러
        """
        if name.startswith("_"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        registered = list(self._repositories.keys()) if self._repositories else []
        raise AttributeError(
            f"'{name}' Repository가 등록되지 않았습니다. "
            f"등록된 Repository: {registered}. "
            f"UnitOfWork 생성 시 repositories 딕셔너리에 '{name}'을 추가하세요."
        )

    @property
    def session(self) -> AsyncSession:
        """현재 활성 세션을 반환한다."""
        if self._session is None:
            raise RuntimeError("UnitOfWork가 시작되지 않았습니다.")
        return self._session

    async def commit(self) -> None:
        """현재 트랜잭션을 커밋한다."""
        await self.session.commit()
        metrics.increment("uow.commit.count")

    async def rollback(self) -> None:
        """현재 트랜잭션을 롤백한다."""
        await self.session.rollback()

    async def flush(self) -> None:
        """세션의 변경 사항을 데이터베이스에 전송한다."""
        await self.session.flush()


class BackgroundUnitOfWork(UnitOfWork):
    """
    백그라운드 작업용 Generic UnitOfWork.

    API 커넥션 풀과 분리된 백그라운드 풀을 사용한다.
    사용 방법은 UnitOfWork와 동일하다.
    """

    async def __aenter__(self) -> Self:
        """백그라운드 세션을 사용하여 컨텍스트에 진입한다."""
        self._start_time = time.perf_counter()

        if self._owns_session:
            self._session = BackgroundSessionLocal()

        for name, repo_class in self._repo_classes.items():
            repo_instance = repo_class(self._session)
            self._repositories[name] = repo_instance
            setattr(self, name, repo_instance)

        return self
```

#### 5.3.2 도메인별 팩토리 함수

```python
# app/user/dependencies.py
"""
User 도메인의 의존성 및 UnitOfWork 팩토리 함수.

이 모듈은 User 도메인에서 사용하는 UnitOfWork 생성 함수를 제공한다.
팩토리 함수를 통해 Repository 구성을 중앙에서 관리하고,
호출 측 코드의 중복을 제거한다.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, BackgroundUnitOfWork
from app.user.repositories.user_repository import UserRepository
from app.user.repositories.user_profile_repository import UserProfileRepository
from app.user.repositories.user_address_repository import UserAddressRepository


class UserUnitOfWorkProtocol(Protocol):
    """
    User 도메인 UnitOfWork의 프로토콜(인터페이스) 정의.

    이 Protocol을 사용하면 Generic UnitOfWork의 타입 안전성 약화를
    부분적으로 보완할 수 있다. 타입 힌트에 이 Protocol을 사용하면
    IDE가 해당 속성들의 존재를 인식한다.

    사용 예시:
        def some_function(uow: UserUnitOfWorkProtocol):
            uow.users.get_by_id(...)  # IDE 자동완성 작동
    """
    users: UserRepository
    profiles: UserProfileRepository
    addresses: UserAddressRepository


def create_user_uow(session: AsyncSession | None = None) -> UnitOfWork:
    """
    User 도메인용 UnitOfWork를 생성한다.

    User 도메인에서 필요한 모든 Repository가 구성된
    UnitOfWork 인스턴스를 반환한다.

    이 팩토리 함수의 장점:
        1. Repository 구성을 한 곳에서 관리
        2. 라우터 코드의 중복 제거
        3. Repository 추가/제거 시 한 곳만 수정

    Args:
        session: 외부에서 주입할 세션. None이면 자동 생성.

    Returns:
        User 도메인용으로 구성된 UnitOfWork 인스턴스

    Example:
        async with create_user_uow(session) as uow:
            user = await uow.users.get_by_id(user_id)
            profile = await uow.profiles.get_by_user_id(user_id)
    """
    return UnitOfWork(
        session=session,
        repositories={
            "users": UserRepository,
            "profiles": UserProfileRepository,
            "addresses": UserAddressRepository,
        }
    )


def create_user_background_uow() -> BackgroundUnitOfWork:
    """
    User 도메인의 백그라운드 작업용 UnitOfWork를 생성한다.

    Returns:
        백그라운드 풀을 사용하는 UnitOfWork 인스턴스
    """
    return BackgroundUnitOfWork(
        repositories={
            "users": UserRepository,
            "profiles": UserProfileRepository,
            "addresses": UserAddressRepository,
        }
    )


def create_user_minimal_uow(session: AsyncSession | None = None) -> UnitOfWork:
    """
    User 도메인의 최소 구성 UnitOfWork를 생성한다.

    사용자 정보만 필요한 API에서 사용하며,
    불필요한 Repository 인스턴스화를 방지한다.

    Returns:
        users Repository만 포함된 UnitOfWork 인스턴스
    """
    return UnitOfWork(
        session=session,
        repositories={
            "users": UserRepository,
        }
    )
```

```python
# app/order/dependencies.py
"""
Order 도메인의 의존성 및 UnitOfWork 팩토리 함수.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork, BackgroundUnitOfWork
from app.order.repositories.order_repository import OrderRepository
from app.order.repositories.order_item_repository import OrderItemRepository
from app.order.repositories.order_status_history_repository import (
    OrderStatusHistoryRepository,
)


class OrderUnitOfWorkProtocol(Protocol):
    """Order 도메인 UnitOfWork의 프로토콜 정의."""
    orders: OrderRepository
    items: OrderItemRepository
    status_history: OrderStatusHistoryRepository


def create_order_uow(session: AsyncSession | None = None) -> UnitOfWork:
    """
    Order 도메인용 UnitOfWork를 생성한다.

    Args:
        session: 외부에서 주입할 세션

    Returns:
        Order 도메인용으로 구성된 UnitOfWork 인스턴스
    """
    return UnitOfWork(
        session=session,
        repositories={
            "orders": OrderRepository,
            "items": OrderItemRepository,
            "status_history": OrderStatusHistoryRepository,
        }
    )


def create_order_background_uow() -> BackgroundUnitOfWork:
    """Order 도메인의 백그라운드 작업용 UnitOfWork를 생성한다."""
    return BackgroundUnitOfWork(
        repositories={
            "orders": OrderRepository,
            "items": OrderItemRepository,
            "status_history": OrderStatusHistoryRepository,
        }
    )
```

#### 5.3.3 라우터에서의 사용

```python
# app/user/api/routers/v1/user.py
"""
User API v1 라우터 (Generic UnitOfWork 패턴 적용).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.user.dependencies import create_user_uow, create_user_minimal_uow
from app.user.services.user_service import UserService
from app.user.schemas import (
    UserCreateRequest,
    UserResponse,
    AddressCreateRequest,
    AddressResponse,
)
from app.core.logging import get_logger

logger = get_logger("user_router")
router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원 가입",
)
async def create_user(
    request: UserCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """
    회원 가입 API.

    팩토리 함수를 사용하여 UnitOfWork를 생성한다.
    팩토리 함수 내부에서 필요한 Repository들이 구성되므로,
    라우터 코드에서는 Repository 목록을 명시할 필요가 없다.
    """
    logger.info(f"[create_user] 요청: email={request.email}")

    # 팩토리 함수로 UnitOfWork 생성
    async with create_user_uow(session) as uow:
        service = UserService(
            user_repo=uow.users,
            profile_repo=uow.profiles,
        )

        user = await service.create_user(
            email=request.email,
            password=request.password,
            nickname=request.nickname,
        )

        await uow.commit()
        return UserResponse.model_validate(user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 조회",
)
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """
    사용자 조회 API.

    조회만 필요한 경우 최소 구성 UnitOfWork를 사용할 수 있다.
    이를 통해 불필요한 Repository 인스턴스화를 방지한다.
    """
    # 최소 구성 UnitOfWork 사용 (users만 필요)
    async with create_user_minimal_uow(session) as uow:
        user = await uow.users.get_by_id_with(
            id=user_id,
            relations=["profile"],
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다."
            )

        return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="배송지 추가",
)
async def add_address(
    user_id: str,
    request: AddressCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> AddressResponse:
    """
    배송지 추가 API.

    이 API는 users와 addresses 두 Repository가 필요하다.
    팩토리 함수가 이미 addresses를 포함하고 있으므로
    추가 설정 없이 사용할 수 있다.
    """
    async with create_user_uow(session) as uow:
        # 사용자 존재 확인
        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다."
            )

        # 기본 배송지 설정 처리
        if request.is_default:
            await uow.addresses.update_by(
                data={"is_default": False},
                user_id=user_id,
                is_default=True,
            )

        # 새 배송지 생성
        address = await uow.addresses.create({
            "user_id": user_id,
            "recipient_name": request.recipient_name,
            "phone": request.phone,
            "address_line1": request.address_line1,
            "address_line2": request.address_line2,
            "postal_code": request.postal_code,
            "is_default": request.is_default,
        })

        await uow.commit()
        return AddressResponse.model_validate(address)
```

#### 5.3.4 크로스 도메인 작업

```python
# app/order/api/routers/v1/order.py
"""
Order API v1 라우터 (Generic UnitOfWork 패턴 적용).

이 예제는 Generic UnitOfWork의 유연성을 보여준다.
크로스 도메인 트랜잭션이 필요한 경우, 새 클래스 생성 없이
딕셔너리에 필요한 Repository를 추가하면 된다.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.database.unit_of_work import UnitOfWork
from app.order.dependencies import create_order_uow
from app.order.repositories.order_repository import OrderRepository
from app.order.repositories.order_item_repository import OrderItemRepository
from app.order.repositories.order_status_history_repository import (
    OrderStatusHistoryRepository,
)
from app.catalog.repositories.product_repository import ProductRepository
from app.catalog.repositories.inventory_repository import InventoryRepository
from app.order.services.order_service import OrderService
from app.order.schemas import OrderCreateRequest, OrderResponse
from app.core.logging import get_logger

logger = get_logger("order_router")
router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="주문 생성",
)
async def create_order(
    request: OrderCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    """
    주문 생성 API (크로스 도메인 트랜잭션 예제).

    주문 생성 시 다음 작업이 하나의 트랜잭션에서 수행되어야 한다:
        1. 상품 정보 조회 (Catalog 도메인)
        2. 재고 확인 및 차감 (Catalog 도메인)
        3. 주문 생성 (Order 도메인)
        4. 주문 항목 생성 (Order 도메인)
        5. 상태 이력 기록 (Order 도메인)

    Generic UnitOfWork 패턴에서는 필요한 Repository들을
    딕셔너리에 추가하기만 하면 된다.
    새로운 UnitOfWork 클래스를 정의할 필요가 없다.
    """
    logger.info(f"[create_order] 요청: user_id={request.user_id}")

    # 크로스 도메인 트랜잭션: Order + Catalog Repository를 함께 사용
    async with UnitOfWork(
        session=session,
        repositories={
            # Order 도메인
            "orders": OrderRepository,
            "items": OrderItemRepository,
            "status_history": OrderStatusHistoryRepository,
            # Catalog 도메인 (크로스 도메인)
            "products": ProductRepository,
            "inventory": InventoryRepository,
        }
    ) as uow:
        # 1. 상품 정보 조회 및 유효성 검증
        product_ids = [item.product_id for item in request.items]
        products = await uow.products.get_by_ids(product_ids)

        if len(products) != len(product_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="존재하지 않는 상품이 포함되어 있습니다."
            )

        # 2. 재고 확인 및 차감
        for item in request.items:
            inventory = await uow.inventory.get_by_product_id(item.product_id)

            if not inventory or inventory.quantity < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"재고가 부족합니다: product_id={item.product_id}"
                )

            # 재고 차감
            await uow.inventory.update(
                id=inventory.id,
                data={"quantity": inventory.quantity - item.quantity}
            )

        # 3. 주문 생성
        product_map = {p.id: p for p in products}
        total_amount = sum(
            product_map[item.product_id].price * item.quantity
            for item in request.items
        )

        order = await uow.orders.create({
            "user_id": request.user_id,
            "total_amount": total_amount,
            "status": "pending",
            "shipping_address_id": request.shipping_address_id,
        })

        # 4. 주문 항목 생성
        for item in request.items:
            product = product_map[item.product_id]
            await uow.items.create({
                "order_id": order.id,
                "product_id": item.product_id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": product.price,
                "subtotal": product.price * item.quantity,
            })

        # 5. 상태 이력 기록
        await uow.status_history.create({
            "order_id": order.id,
            "status": "pending",
            "note": "주문 접수 완료",
        })

        await uow.commit()

        logger.info(f"[create_order] 완료: order_id={order.id}")
        return OrderResponse.model_validate(order)
```

---

## 6. 결론 및 권장사항

### 6.1 패턴 선택 기준

프로젝트의 특성과 팀의 상황에 따라 적합한 패턴이 다르다. 다음 기준을 참고하여 선택한다.

옵션 2(도메인별 UnitOfWork)를 선택해야 하는 경우는 다음과 같다.

첫째, 팀 규모가 3명 이상이고 도메인별로 업무가 분담되는 경우이다. 각 도메인의 경계가 UnitOfWork 클래스로 명확히 구분되어 있어 팀원 간 충돌이 줄어든다.

둘째, 프로젝트 수명이 1년 이상으로 예상되는 장기 프로젝트인 경우이다. 타입 안전성과 IDE 지원이 장기적인 유지보수성에 기여한다.

셋째, 주니어 개발자가 팀에 있는 경우이다. 직관적인 구조로 학습 곡선이 낮아 새 팀원의 온보딩이 용이하다.

넷째, 코드 리뷰 문화가 활성화된 팀인 경우이다. 명시적인 타입 선언이 코드 리뷰의 효율성을 높인다.

옵션 3(Generic UnitOfWork)를 선택해야 하는 경우는 다음과 같다.

첫째, 팀 규모가 1-2명의 소규모 팀인 경우이다. 보일러플레이트 코드를 최소화하여 빠른 개발이 가능하다.

둘째, 요구사항이 자주 변경되는 초기 스타트업 환경인 경우이다. 새 클래스 생성 없이 딕셔너리 수정만으로 빠르게 대응할 수 있다.

셋째, 크로스 도메인 트랜잭션이 빈번한 경우이다. 필요한 Repository 조합을 유연하게 구성할 수 있다.

넷째, 테스트에서 다양한 Mock 조합이 필요한 경우이다. 딕셔너리 교체만으로 간편하게 Mock을 구성할 수 있다.

### 6.2 하이브리드 접근

두 패턴의 장점을 결합한 하이브리드 접근도 가능하다. 기본적으로 옵션 2의 도메인별 UnitOfWork를 사용하되, 크로스 도메인 트랜잭션이 필요한 특수한 경우에만 옵션 3의 Generic UnitOfWork를 사용하는 방식이다.

```python
# 일반적인 경우: 도메인별 UnitOfWork 사용
async with UserUnitOfWork(session) as uow:
    ...

# 특수한 경우: Generic UnitOfWork로 크로스 도메인 처리
async with UnitOfWork(
    session=session,
    repositories={
        "orders": OrderRepository,
        "inventory": InventoryRepository,  # 다른 도메인
    }
) as uow:
    ...
```

### 6.3 최종 권장사항

본 문서에서 다룬 E-Commerce 플랫폼과 같은 중대형 프로젝트에서는 옵션 2(도메인별 UnitOfWork)를 기본으로 권장한다. 타입 안전성, IDE 지원, 도메인 경계 명확화의 이점이 추가 파일 관리 비용을 상회하기 때문이다.

다만, 팀의 상황과 프로젝트의 특성을 고려하여 최종 결정을 내려야 한다. 어떤 패턴을 선택하든 일관성 있게 적용하는 것이 중요하며, 팀 내 합의를 통해 선택한 패턴을 문서화하고 준수해야 한다.
