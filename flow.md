# AsyncGenerator vs Context Manager 세션 관리 패턴 비교

## 1. 현재 프로젝트의 두 가지 세션 관리 패턴

### 패턴 A: AsyncGenerator 사용 (session.py:156)

```python
from typing import AsyncGenerator

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session  # 제너레이터 - AsyncGenerator 타입 필요
        except Exception as e:
            await session.rollback()
            raise e
```

**특징:**
- FastAPI의 `Depends()` 의존성 주입용
- `yield` 키워드 사용 → 비동기 제너레이터
- 타입 힌트로 `AsyncGenerator[AsyncSession, None]` 필요

---

### 패턴 B: Context Manager 사용 (unit_of_work.py:18)

```python
# AsyncGenerator import 불필요!
from typing import Self

class UnitOfWork:
    async def __aenter__(self) -> Self:
        self._session = AsyncSessionLocal()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            await self.rollback()
        await self._session.close()
```

**특징:**
- `AsyncGenerator` 타입 힌트 불필요
- `__aenter__` / `__aexit__` 매직 메서드로 컨텍스트 관리
- `yield` 없이 직접 세션 객체 관리

---

## 2. 실제 사용 흐름 비교

### AsyncGenerator 패턴 (FastAPI Depends)

```
┌─────────────────┐     Depends()      ┌──────────────┐
│  FastAPI Route  │ ─────────────────→ │  get_session │
└─────────────────┘                    └──────────────┘
                                              │
                                              │ yield session
                                              ▼
                                       ┌──────────────┐
                                       │ Route Handler│
                                       │   실행       │
                                       └──────────────┘
                                              │
                                              │ 요청 완료
                                              ▼
                                       ┌──────────────┐
                                       │ 세션 자동    │
                                       │ 정리/롤백    │
                                       └──────────────┘
```

```python
# router.py
@router.get("/logs")
async def get_logs(session: AsyncSession = Depends(get_session)):
    repo = UserAccessLogRepository(session)
    return await repo.get_recent_logs()
```

---

### Context Manager 패턴 (UnitOfWork)

```
┌─────────────────┐     async with     ┌──────────────┐
│  Service/Task   │ ─────────────────→ │  UnitOfWork  │
└─────────────────┘                    └──────────────┘
                                              │
                                              │ __aenter__
                                              │ (세션 생성)
                                              ▼
                                       ┌──────────────┐
                                       │  Repository  │
                                       │   작업 실행  │
                                       └──────────────┘
                                              │
                                              │ commit/rollback
                                              ▼
                                       ┌──────────────┐
                                       │  __aexit__   │
                                       │ (세션 정리)  │
                                       └──────────────┘
```

```python
# service.py 또는 background task
async def save_access_log(data: dict):
    async with UnitOfWork() as uow:
        await uow.user_access_logs.create(data)
        await uow.commit()
```

---

## 3. user_access_log_repository.py 분석

```python
# user_access_log_repository.py:29-36
class UserAccessLogRepository(BaseRepository[UserAccessLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
```

**Repository는 세션 관리 방식에 무관하게 동작:**

| 구분 | AsyncGenerator 패턴 | Context Manager 패턴 |
|------|---------------------|---------------------|
| 세션 공급원 | `get_session()` | `UnitOfWork._session` |
| Repository 초기화 | `Depends()`가 주입 | `UnitOfWork._init_repositories()` |
| 세션 사용 | 동일 (`self.session.execute()`) | 동일 |

Repository는 **세션을 주입받아 사용**할 뿐, 어떻게 생성되었는지 알 필요 없음.

---

## 4. AsyncGenerator가 없다면?

### 변경이 필요한 부분

```python
# session.py - 현재
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    yield session  # ← yield 사용 = 제너레이터

# session.py - AsyncGenerator 없이 (불가능한 조합)
async def get_session() -> ???:
    yield session  # yield가 있으면 반드시 Generator 타입 필요
```

**결론:** `yield`를 사용하면 반드시 `AsyncGenerator` 타입 힌트 필요.

---

### 대안: UnitOfWork 패턴으로 전환

```
┌─────────────────────────────────────────────────────────────┐
│                    AsyncGenerator 없는 구조                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐                                           │
│  │   Router    │                                           │
│  └──────┬──────┘                                           │
│         │                                                   │
│         │ async with UnitOfWork() as uow:                  │
│         ▼                                                   │
│  ┌─────────────────────────────────────┐                   │
│  │           UnitOfWork                │                   │
│  │  ┌─────────────────────────────┐   │                   │
│  │  │ __aenter__                  │   │                   │
│  │  │  - AsyncSessionLocal()      │   │                   │
│  │  │  - Repository 초기화        │   │                   │
│  │  └─────────────────────────────┘   │                   │
│  │  ┌─────────────────────────────┐   │                   │
│  │  │ user_access_logs Repository │   │                   │
│  │  │  - session 주입받아 사용    │   │                   │
│  │  └─────────────────────────────┘   │                   │
│  │  ┌─────────────────────────────┐   │                   │
│  │  │ __aexit__                   │   │                   │
│  │  │  - rollback (예외 시)       │   │                   │
│  │  │  - session.close()          │   │                   │
│  │  └─────────────────────────────┘   │                   │
│  └─────────────────────────────────────┘                   │
│                                                             │
│  ※ yield 없음 → AsyncGenerator 불필요                      │
│  ※ __aenter__/__aexit__로 세션 라이프사이클 관리            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 두 패턴 비교 요약

| 항목 | AsyncGenerator (yield) | Context Manager (UnitOfWork) |
|------|------------------------|------------------------------|
| **타입 import** | `from typing import AsyncGenerator` | 불필요 |
| **세션 생성** | `yield session` | `self._session = AsyncSessionLocal()` |
| **FastAPI Depends** | 직접 지원 | 직접 사용 불가 (래퍼 필요) |
| **트랜잭션 경계** | 요청 단위 (암묵적) | 명시적 (`commit()` 호출) |
| **다중 Repository** | 각각 세션 주입 | UnitOfWork가 통합 관리 |
| **백그라운드 태스크** | `get_background_session()` | `BackgroundUnitOfWork()` |

---

## 6. 권장 사용 패턴

```
┌─────────────────────────────────────────────────────────────┐
│                      사용 시나리오                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 단순 조회 API                                           │
│     → AsyncGenerator + Depends (현재 get_session)          │
│     → 간단하고 FastAPI와 자연스럽게 통합                    │
│                                                             │
│  2. 복잡한 비즈니스 로직 (다중 Repository 사용)             │
│     → UnitOfWork 패턴                                       │
│     → 트랜잭션 경계 명확, Repository 통합 관리             │
│                                                             │
│  3. 백그라운드 태스크 (로그 저장 등)                        │
│     → BackgroundUnitOfWork                                  │
│     → 메인 풀과 분리된 커넥션 풀 사용                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 결론

`AsyncGenerator`는 **yield를 사용하는 비동기 함수의 타입 힌트**로 필수적입니다.

만약 `AsyncGenerator`를 사용하지 않으려면:
1. `yield` 대신 `__aenter__`/`__aexit__` 매직 메서드를 구현한 **클래스 기반 Context Manager** 사용
2. 이 프로젝트에서는 이미 `UnitOfWork` 패턴이 이 방식으로 구현되어 있음
3. Repository(`UserAccessLogRepository`)는 세션을 주입받아 사용하므로, 어떤 패턴을 사용해도 동일하게 동작
