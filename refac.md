# UnitOfWork 리팩토링 문서

본 문서는 UnitOfWork 패턴을 중앙집중식에서 도메인별 분리 방식으로 리팩토링한 내용을 기록한다.

---

## 1. 리팩토링 배경 및 이유

### 1.1 기존 설계의 문제점

기존 구조에서는 `app/database/unit_of_work.py`에 단일 `UnitOfWork` 클래스가 정의되어 있었으며, 이 클래스 내부에서 Home 도메인의 `UserAccessLogRepository`를 직접 import하고 초기화하고 있었다.

```python
# 기존 코드 (app/database/unit_of_work.py)
class UnitOfWork:
    def _init_repositories(self) -> None:
        from app.home.repositories.user_access_log_repository import (
            UserAccessLogRepository,
        )
        self.user_access_logs = UserAccessLogRepository(self._session)
```

이 설계에는 다음과 같은 문제점이 있었다.

첫째, 의존성 방향이 역전되어 있었다. 인프라 계층(database)이 도메인 계층(home)을 알고 있었다. 올바른 의존성 방향은 도메인이 인프라에 의존하는 것이지, 인프라가 도메인에 의존하는 것이 아니다.

```
문제가 있던 의존성 방향:
    app/database/unit_of_work.py  -->  app/home/repositories/...

올바른 의존성 방향:
    app/home/unit_of_work.py  -->  app/database/unit_of_work.py
```

둘째, 확장성 문제가 있었다. 새로운 도메인(user, blog, sns 등)이 추가될 때마다 `app/database/unit_of_work.py` 파일을 수정해야 했다. 이는 단일 책임 원칙(SRP)을 위반하며, 도메인 간 불필요한 결합을 야기한다.

셋째, 위치와 내용의 불일치가 있었다. `app/database/` 폴더에 위치하여 범용 인프라 모듈처럼 보이지만, 실제로는 특정 도메인(home)의 Repository를 하드코딩하고 있었다.

### 1.2 리팩토링 목표

본 리팩토링의 목표는 다음과 같다.

첫째, 의존성 방향을 정상화한다. 인프라 계층은 도메인을 알지 못하고, 도메인이 인프라를 사용하도록 한다.

둘째, 도메인 독립성을 확보한다. 각 도메인은 자신만의 UnitOfWork를 가지며, 다른 도메인의 존재를 알 필요가 없다.

셋째, 확장성을 개선한다. 새로운 도메인 추가 시 기존 코드 수정 없이 해당 도메인 폴더에만 새 UnitOfWork를 추가하면 된다.

---

## 2. 변경 사항 요약

### 2.1 파일 변경 목록

| 파일 경로 | 변경 유형 | 설명 |
|-----------|----------|------|
| `app/database/unit_of_work.py` | 수정 | `UnitOfWork` -> `BaseUnitOfWork`로 변경, Repository 제거 |
| `app/home/unit_of_work.py` | 신규 | `HomeUnitOfWork`, `HomeBackgroundUnitOfWork` 정의 |
| `app/home/api/routers/v1/home.py` | 수정 | `UnitOfWork` -> `HomeUnitOfWork`로 변경 |
| `app/core/middlewares/user_info_middleware.py` | 수정 | `BackgroundUnitOfWork` -> `HomeBackgroundUnitOfWork`로 변경 |
| `app/database/__init__.py` | 수정 | export 항목 변경 |

### 2.2 클래스 이름 변경

| 기존 클래스명 | 신규 클래스명 | 위치 |
|--------------|--------------|------|
| `UnitOfWork` | `BaseUnitOfWork` | `app/database/unit_of_work.py` |
| `BackgroundUnitOfWork` | `BaseBackgroundUnitOfWork` | `app/database/unit_of_work.py` |
| (없음) | `HomeUnitOfWork` | `app/home/unit_of_work.py` |
| (없음) | `HomeBackgroundUnitOfWork` | `app/home/unit_of_work.py` |

---

## 3. 상세 변경 내용

### 3.1 app/database/unit_of_work.py

#### 변경 전

```python
class UnitOfWork:
    def _init_repositories(self) -> None:
        from app.home.repositories.user_access_log_repository import (
            UserAccessLogRepository,
        )
        self.user_access_logs = UserAccessLogRepository(self._session)

class BackgroundUnitOfWork(UnitOfWork):
    ...
```

#### 변경 후

```python
class BaseUnitOfWork:
    # Repository 초기화 로직 제거
    # 세션 관리와 트랜잭션 제어만 담당

class BaseBackgroundUnitOfWork(BaseUnitOfWork):
    # 백그라운드 전용 세션 사용
```

#### 변경 이유

기반 클래스는 세션 관리와 트랜잭션 제어라는 공통 기능만 제공해야 한다. Repository는 도메인별로 다르므로, 각 도메인의 하위 클래스에서 정의하는 것이 적합하다.

클래스 이름에 `Base` 접두사를 추가하여 이 클래스가 직접 사용되는 것이 아니라 상속을 위한 기반 클래스임을 명확히 했다.

### 3.2 app/home/unit_of_work.py (신규)

```python
class HomeUnitOfWork(BaseUnitOfWork):
    user_access_logs: UserAccessLogRepository

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.user_access_logs = UserAccessLogRepository(self._session)
        return self

class HomeBackgroundUnitOfWork(BaseBackgroundUnitOfWork):
    user_access_logs: UserAccessLogRepository

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.user_access_logs = UserAccessLogRepository(self._session)
        return self
```

#### 설계 근거

Home 도메인 전용 UnitOfWork를 생성하여 다음을 달성한다.

첫째, 타입 안전성을 확보한다. `user_access_logs` 속성이 클래스에 명시적으로 선언되어 있어 IDE 자동완성과 타입 검사가 완벽하게 작동한다.

둘째, 도메인 캡슐화를 달성한다. Home 도메인에서 필요한 Repository만 이 UnitOfWork에 포함된다. 다른 도메인의 Repository는 알지 못한다.

셋째, 명확한 책임 분리를 이룬다. 이 파일을 보면 Home 도메인에서 어떤 데이터에 접근하는지 즉시 파악할 수 있다.

### 3.3 app/home/api/routers/v1/home.py

#### 변경 전

```python
from app.database.unit_of_work import UnitOfWork

async with UnitOfWork(session) as uow:
    service = UserAccessLogService(uow.user_access_logs)
```

#### 변경 후

```python
from app.home.unit_of_work import HomeUnitOfWork

async with HomeUnitOfWork(session) as uow:
    service = UserAccessLogService(uow.user_access_logs)
```

#### 변경 이유

라우터는 자신이 속한 도메인의 UnitOfWork를 사용해야 한다. 이를 통해 도메인 경계가 명확해지고, 어떤 데이터에 접근하는지 코드에서 명시적으로 드러난다.

### 3.4 app/core/middlewares/user_info_middleware.py

#### 변경 전

```python
from app.database.unit_of_work import BackgroundUnitOfWork

async with BackgroundUnitOfWork() as uow:
    ...
```

#### 변경 후

```python
from app.home.unit_of_work import HomeBackgroundUnitOfWork

async with HomeBackgroundUnitOfWork() as uow:
    ...
```

#### 변경 이유

미들웨어가 Home 도메인의 접속 로그를 저장하므로, Home 도메인의 BackgroundUnitOfWork를 사용하는 것이 논리적으로 맞다. 이를 통해 미들웨어가 어떤 도메인의 데이터를 다루는지 명확해진다.

### 3.5 app/database/__init__.py

#### 변경 전

```python
from app.database.unit_of_work import UnitOfWork, BackgroundUnitOfWork

__all__ = [
    ...
    "UnitOfWork",
    "BackgroundUnitOfWork",
]
```

#### 변경 후

```python
from app.database.unit_of_work import BaseUnitOfWork, BaseBackgroundUnitOfWork

__all__ = [
    ...
    "BaseUnitOfWork",
    "BaseBackgroundUnitOfWork",
]
```

#### 변경 이유

database 패키지에서 export하는 UnitOfWork는 이제 기반 클래스이므로 이름을 변경했다. 실제 사용은 각 도메인의 UnitOfWork를 통해 이루어진다.

---

## 4. 리팩토링 후 구조

### 4.1 디렉토리 구조

```
app/
├── database/
│   ├── __init__.py
│   ├── session.py
│   ├── unit_of_work.py          # BaseUnitOfWork, BaseBackgroundUnitOfWork
│   └── repositories/
│       └── base.py              # BaseRepository
│
├── home/
│   ├── __init__.py
│   ├── unit_of_work.py          # HomeUnitOfWork, HomeBackgroundUnitOfWork (신규)
│   ├── repositories/
│   │   └── user_access_log_repository.py
│   ├── services/
│   │   └── user_access_log_service.py
│   └── api/
│       └── routers/
│           └── v1/
│               └── home.py
│
├── user/                         # 향후 확장 시
│   └── unit_of_work.py          # UserUnitOfWork 정의 예정
│
└── blog/                         # 향후 확장 시
    └── unit_of_work.py          # BlogUnitOfWork 정의 예정
```

### 4.2 의존성 흐름

```
                    app/database/
                    ┌─────────────────────────────┐
                    │ BaseUnitOfWork              │
                    │ BaseBackgroundUnitOfWork    │
                    │ BaseRepository              │
                    └─────────────────────────────┘
                              ^
                              │ 상속
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
    v                         v                         v
app/home/               app/user/               app/blog/
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│HomeUnitOfWork │       │UserUnitOfWork │       │BlogUnitOfWork │
│  - user_      │       │  - users      │       │  - posts      │
│    access_logs│       │  - profiles   │       │  - comments   │
└───────────────┘       └───────────────┘       └───────────────┘
```

---

## 5. 새로운 도메인 추가 가이드

향후 새로운 도메인(예: user, blog)을 추가할 때는 다음 단계를 따른다.

### 5.1 도메인 UnitOfWork 생성

```python
# app/user/unit_of_work.py
from typing import Self

from app.database.unit_of_work import BaseUnitOfWork
from app.user.repositories.user_repository import UserRepository
from app.user.repositories.user_profile_repository import UserProfileRepository


class UserUnitOfWork(BaseUnitOfWork):
    """User 도메인 전용 UnitOfWork."""

    users: UserRepository
    profiles: UserProfileRepository

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.users = UserRepository(self._session)
        self.profiles = UserProfileRepository(self._session)
        return self
```

### 5.2 라우터에서 사용

```python
# app/user/api/routers/v1/user.py
from app.user.unit_of_work import UserUnitOfWork

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    async with UserUnitOfWork(session) as uow:
        user = await uow.users.get_by_id(user_id)
        return user
```

### 5.3 기존 코드 수정 불필요

새로운 도메인을 추가할 때 `app/database/unit_of_work.py`나 다른 도메인의 코드를 수정할 필요가 없다. 이것이 도메인별 UnitOfWork 패턴의 핵심 장점이다.

---

## 6. 마이그레이션 체크리스트

리팩토링 완료 후 확인이 필요한 항목은 다음과 같다.

- [x] `app/database/unit_of_work.py` - BaseUnitOfWork로 변경
- [x] `app/home/unit_of_work.py` - 신규 생성
- [x] `app/home/api/routers/v1/home.py` - HomeUnitOfWork 사용
- [x] `app/core/middlewares/user_info_middleware.py` - HomeBackgroundUnitOfWork 사용
- [x] `app/database/__init__.py` - export 항목 변경
- [ ] 테스트 실행 및 검증
- [ ] 기존 기능 동작 확인

---

## 7. 결론

본 리팩토링을 통해 다음을 달성했다.

첫째, 의존성 방향이 정상화되었다. 인프라 계층(database)은 더 이상 도메인 계층을 알지 못한다.

둘째, 도메인 독립성이 확보되었다. 각 도메인은 자신만의 UnitOfWork를 가지며, 다른 도메인에 영향을 주지 않고 독립적으로 발전할 수 있다.

셋째, 확장성이 개선되었다. 새로운 도메인 추가 시 해당 도메인 폴더에 UnitOfWork를 생성하기만 하면 되며, 기존 코드 수정이 필요하지 않다.

넷째, 코드의 의도가 명확해졌다. 각 라우터에서 어떤 도메인의 UnitOfWork를 사용하는지 코드에서 명시적으로 드러난다.

---

## 8. 추가 변경: 도메인 UnitOfWork 파일 위치 이동

### 8.1 변경 내용

| 변경 전 | 변경 후 |
|---------|---------|
| `app/home/unit_of_work.py` | `app/home/services/home_unit_of_work.py` |

### 8.2 변경 이유

도메인 UnitOfWork는 서비스 계층에서 트랜잭션 경계를 관리하는 역할을 하므로, `services/` 폴더 내에 위치하는 것이 논리적으로 더 적합하다. 또한 파일명에 `home_` 접두사를 추가하여 도메인 소속을 파일명 자체에서도 식별할 수 있게 했다.

### 8.3 import 경로 변경

| 파일 | 변경 전 | 변경 후 |
|------|---------|---------|
| `app/home/api/routers/v1/home.py` | `from app.home.unit_of_work import HomeUnitOfWork` | `from app.home.services.home_unit_of_work import HomeUnitOfWork` |
| `app/core/middlewares/user_info_middleware.py` | `from app.home.unit_of_work import HomeBackgroundUnitOfWork` | `from app.home.services.home_unit_of_work import HomeBackgroundUnitOfWork` |

### 8.4 변경 후 디렉토리 구조

```
app/home/
├── __init__.py
├── api/
│   └── routers/
│       └── v1/
│           └── home.py
├── repositories/
│   └── user_access_log_repository.py
└── services/
    ├── base.py
    ├── home_unit_of_work.py          # HomeUnitOfWork, HomeBackgroundUnitOfWork
    └── user_access_log_service.py
```
