# 성능 체크리스트

## 데이터베이스 최적화

### N+1 쿼리 탐지

#### 증상
```python
# 이 코드는 N+1 쿼리 발생!
users = await session.execute(select(User))
for user in users.scalars():
    # 매 루프마다 추가 쿼리 발생
    print(user.orders)  # lazy loading
```

#### 해결 방법
```python
# ✅ selectinload - 별도 IN 쿼리로 관계 로딩
stmt = select(User).options(selectinload(User.orders))

# ✅ joinedload - JOIN으로 한 번에 로딩 (1:1, N:1 관계에 적합)
stmt = select(Order).options(joinedload(Order.user))

# ✅ subqueryload - 서브쿼리로 로딩
stmt = select(User).options(subqueryload(User.orders))
```

#### 로딩 전략 선택 가이드

| 관계 유형 | 권장 전략 | 이유 |
|-----------|-----------|------|
| 1:1, N:1 | `joinedload` | 단일 JOIN으로 효율적 |
| 1:N (소량) | `selectinload` | IN 쿼리로 깔끔 |
| 1:N (대량) | `subqueryload` | 메모리 효율적 |
| N:M | `selectinload` | 중간 테이블 포함 효율적 로딩 |

---

### 인덱스 전략

#### 체크 항목
- [ ] WHERE 절 컬럼에 인덱스 존재
- [ ] ORDER BY 컬럼에 인덱스 존재
- [ ] 복합 인덱스 컬럼 순서 최적화
- [ ] 커버링 인덱스 활용

```python
# 인덱스 정의
class User(Base):
    __table_args__ = (
        # 단일 컬럼 인덱스
        Index("ix_users_email", "email"),

        # 복합 인덱스 (순서 중요!)
        Index("ix_users_status_created", "status", "created_at"),

        # 부분 인덱스
        Index(
            "ix_users_active_email",
            "email",
            postgresql_where=text("status = 'active'")
        ),
    )
```

#### 복합 인덱스 컬럼 순서
```sql
-- 쿼리 패턴
SELECT * FROM users WHERE status = 'active' ORDER BY created_at DESC

-- 최적 인덱스: (status, created_at)
-- status가 앞에 와야 함 (equality before range)
```

---

### 쿼리 최적화

#### 필요한 컬럼만 조회
```python
# ❌ 모든 컬럼 조회
users = await session.execute(select(User))

# ✅ 필요한 컬럼만
stmt = select(User.id, User.name, User.email)
```

#### 카운트 최적화
```python
# ❌ 전체 로드 후 카운트
users = await session.execute(select(User))
count = len(list(users.scalars()))

# ✅ COUNT 쿼리
count = await session.scalar(
    select(func.count()).select_from(User)
)
```

#### EXISTS vs COUNT
```python
# ❌ COUNT로 존재 여부 확인
count = await session.scalar(
    select(func.count()).where(User.email == email)
)
exists = count > 0

# ✅ EXISTS 사용
exists = await session.scalar(
    select(exists().where(User.email == email))
)
```

---

## 비동기 최적화

### 동기 코드 탐지

```python
# ❌ 블로킹 동기 코드
import time
import requests

async def process():
    time.sleep(1)  # 블로킹!
    response = requests.get(url)  # 블로킹!

# ✅ 비동기 처리
import asyncio
import httpx

async def process():
    await asyncio.sleep(1)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
```

### 병렬 처리

```python
# ❌ 순차 실행
user = await get_user(user_id)
orders = await get_orders(user_id)
stats = await get_stats(user_id)

# ✅ 병렬 실행
user, orders, stats = await asyncio.gather(
    get_user(user_id),
    get_orders(user_id),
    get_stats(user_id),
)
```

### 동시성 제한

```python
# ❌ 무제한 동시 요청
results = await asyncio.gather(
    *[fetch(url) for url in urls]  # 1000개 동시 요청?
)

# ✅ Semaphore로 제한
semaphore = asyncio.Semaphore(10)

async def limited_fetch(url):
    async with semaphore:
        return await fetch(url)

results = await asyncio.gather(
    *[limited_fetch(url) for url in urls]
)
```

---

## 메모리 최적화

### 대량 데이터 처리

```python
# ❌ 전체 메모리 로드
all_users = list(await session.execute(select(User)))
for user in all_users:
    process(user)

# ✅ 스트리밍 처리
result = await session.stream(select(User))
async for user in result.scalars():
    process(user)

# ✅ 배치 처리
async def process_in_batches(batch_size: int = 100):
    offset = 0
    while True:
        stmt = select(User).offset(offset).limit(batch_size)
        result = await session.execute(stmt)
        users = list(result.scalars())

        if not users:
            break

        for user in users:
            process(user)

        offset += batch_size
```

### 제너레이터 활용

```python
# ❌ 리스트 반환
def get_all_items() -> list[Item]:
    return [Item(i) for i in range(1000000)]

# ✅ 제너레이터 반환
def get_all_items() -> Iterator[Item]:
    for i in range(1000000):
        yield Item(i)

# ✅ 비동기 제너레이터
async def get_all_items() -> AsyncIterator[Item]:
    async for row in stream_from_db():
        yield Item(row)
```

---

## 캐싱 전략

### 캐시 적용 대상

| 대상 | 캐시 전략 | TTL |
|------|-----------|-----|
| 설정/메타데이터 | 애플리케이션 캐시 | 긴 TTL (시간~일) |
| 사용자 세션 | Redis | 세션 만료 시간 |
| 자주 조회되는 데이터 | Redis | 중간 TTL (분~시간) |
| 계산 비용 높은 결과 | Redis | 결과 유효 기간 |

### 캐시 패턴

```python
from functools import lru_cache
from cachetools import TTLCache
import redis.asyncio as redis

# 애플리케이션 레벨 캐시 (메모리)
@lru_cache(maxsize=100)
def get_config(key: str) -> str:
    return load_config(key)

# TTL 캐시
cache = TTLCache(maxsize=1000, ttl=300)

async def get_user_cached(user_id: int) -> User:
    if user_id in cache:
        return cache[user_id]

    user = await get_user(user_id)
    cache[user_id] = user
    return user

# Redis 캐시
async def get_user_redis(user_id: int) -> User:
    key = f"user:{user_id}"

    # 캐시 조회
    cached = await redis_client.get(key)
    if cached:
        return User.model_validate_json(cached)

    # DB 조회 후 캐시
    user = await get_user_from_db(user_id)
    await redis_client.setex(key, 300, user.model_dump_json())
    return user
```

### 캐시 무효화

```python
# 데이터 변경 시 캐시 무효화
async def update_user(user_id: int, data: UserUpdate) -> User:
    user = await update_user_in_db(user_id, data)

    # 캐시 무효화
    await redis_client.delete(f"user:{user_id}")
    await redis_client.delete(f"user_list:*")  # 패턴 삭제

    return user
```

---

## 페이지네이션

### Offset vs Cursor

```python
# Offset 기반 (작은 데이터셋)
stmt = select(User).offset((page - 1) * size).limit(size)

# Cursor 기반 (대용량, 실시간)
stmt = (
    select(User)
    .where(User.id > last_id)
    .order_by(User.id)
    .limit(size)
)
```

### 전체 카운트 최적화

```python
# ❌ 매 요청마다 COUNT
total = await session.scalar(select(func.count()).select_from(User))

# ✅ 캐시된 카운트 (근사치)
total = await redis_client.get("user_count")
if not total:
    total = await session.scalar(select(func.count()).select_from(User))
    await redis_client.setex("user_count", 60, total)

# ✅ 또는 카운트 생략 (has_more만 반환)
items = await session.execute(
    select(User).limit(size + 1)  # 1개 더 조회
)
items = list(items.scalars())
has_more = len(items) > size
items = items[:size]
```

---

## 응답 최적화

### 응답 압축

```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### 지연 로딩 API

```python
# ❌ 모든 관계 즉시 로딩
class UserResponse(BaseModel):
    orders: list[OrderResponse]
    reviews: list[ReviewResponse]
    activities: list[ActivityResponse]

# ✅ 필요 시 별도 엔드포인트
@router.get("/users/{id}")
async def get_user(id: int) -> UserResponse: ...

@router.get("/users/{id}/orders")
async def get_user_orders(id: int) -> list[OrderResponse]: ...
```
