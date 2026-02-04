# 프로젝트 리팩토링 보고서

> 작성일: 2024-02-04
> 대상: FastAPI Default Project Structure

---

## 1. 프로젝트 개요

### 1.1 프로젝트 구조
```
fastapi-default-project-structure/
├── app/
│   ├── core/                    # 핵심 모듈 (미들웨어, 예외)
│   ├── database/                # DB 세션, Repository, UoW
│   ├── dependencies/            # FastAPI 의존성 주입
│   ├── utils/                   # 유틸리티 (로거, 페이지네이션)
│   ├── home/                    # Home 도메인 모듈
│   ├── user/                    # User 도메인 모듈 (미구현)
│   ├── blog/                    # Blog 도메인 모듈 (미구현)
│   ├── sns/                     # SNS 도메인 모듈 (미구현)
│   └── reply/                   # Reply 도메인 모듈 (미구현)
├── config.py                    # Pydantic Settings
├── main.py                      # FastAPI 앱 진입점
└── tests/                       # 테스트 (미구현)
```

### 1.2 아키텍처 패턴
```
Request → Router → UnitOfWork → Service → Repository → Database
                                    ↓
Response ← Router ← Service ← Repository ←
```

### 1.3 기술 스택
- **Framework**: FastAPI
- **ORM**: SQLAlchemy 2.0 (비동기)
- **Database**: MySQL (aiomysql)
- **Validation**: Pydantic v2
- **Documentation**: Scalar API

---

## 2. 코드 리뷰 리포트

### 2.1 검사 결과 요약

| 항목 | 상태 | 점수 |
|------|------|------|
| 코드 품질 | 양호 | ⭐⭐⭐⭐☆ |
| 보안 | 개선 필요 | ⭐⭐⭐☆☆ |
| 성능 | 양호 | ⭐⭐⭐⭐☆ |
| 가독성 | 우수 | ⭐⭐⭐⭐⭐ |
| 테스트 | 미흡 | ⭐☆☆☆☆ |

---

### 2.2 🔴 Critical (즉시 수정 필요)

| 파일:라인 | 문제 | 설명 | 개선 방안 |
|-----------|------|------|----------|
| `.env:11` | 오타 | `DEBU="False"` → `DEBUG` 오타 | `DEBUG="False"`로 수정 |
| `.env:23` | 보안 | DB 비밀번호 평문 노출 (`DB_PASSWORD="1324"`) | `.env.example`로 분리, `.env`는 `.gitignore`에 추가 |
| `.env:45` | 보안 | 세션 시크릿 키 하드코딩 | 환경별로 다른 시크릿 키 사용, 운영 환경에서는 강력한 키 생성 |
| `.env:102-104` | 보안 | JWT 시크릿 키 평문 (`secretkey`) | `openssl rand -hex 32`로 생성한 강력한 키 사용 |
| `app/dependencies/auth.py` | 미구현 | 인증 모듈이 비어있음 | 인증/인가 로직 구현 필요 |
| `tests/` | 미구현 | 테스트 코드 없음 | 단위/통합 테스트 작성 필요 |

---

### 2.3 🟡 Warning (권장 수정)

| 파일:라인 | 문제 | 설명 | 개선 방안 |
|-----------|------|------|----------|
| `app/home/models/models.py:191` | 타임존 불일치 | `func.now()` 사용 (DB 서버 시간) | `timezone_settings.now()` 사용으로 통일 |
| `config.py:145` | CORS 보안 | `CORS_ALLOW_ORIGINS=["*"]` + `allow_credentials=True` | 운영 환경에서는 특정 도메인만 허용 |
| `app/database/session.py:68-81` | 설정 분리 | DB 연결 설정이 하드코딩됨 | `config.py`에서 `pool_size`, `max_overflow` 등 관리 |
| `app/home/api/routers/v1/home.py` | Rate Limiting 없음 | 접속 로그 API에 Rate Limit 미적용 | `slowapi` 등으로 Rate Limiting 추가 |
| `app/core/middlewares/user_info_middleware.py:247` | 에러 처리 | `asyncio.create_task()` 에러가 로그에만 기록 | 에러 모니터링 시스템 연동 (Sentry 등) |
| 전체 도메인 모듈 | 중복 코드 | 각 모듈에 동일한 `base.py` 파일 존재 | 공통 `base.py`를 `app/database/models/base.py`로 통합 |
| `app/database/repositories/base.py:172-173` | UUID 문자열 변환 | `str(uuid4())` 매번 호출 | ID 생성 전략을 설정으로 분리 |

---

### 2.4 🟢 Info (참고 사항)

| 파일:라인 | 내용 |
|-----------|------|
| `main.py:69-70` | Swagger UI 비활성화 후 Scalar 사용 - 좋은 선택 |
| `app/database/session.py` | 메인/백그라운드 커넥션 풀 분리 - 우수한 설계 |
| `app/database/unit_of_work.py` | UoW 패턴 적용 - 트랜잭션 관리 용이 |
| `config.py` | Pydantic Settings로 타입 안전한 설정 관리 |
| `app/utils/logger.py` | 날짜별 로그 파일 분리, 타임존 적용 |

---

## 3. 설계 검토 리포트

### 3.1 아키텍처 분석

#### 3.1.1 장점
1. **레이어드 아키텍처**: Router → Service → Repository 명확한 분리
2. **Unit of Work 패턴**: 트랜잭션 경계 관리 용이
3. **Generic Repository**: 코드 재사용성 높음
4. **커넥션 풀 분리**: 메인/백그라운드 풀 분리로 안정성 확보
5. **타입 안전성**: Pydantic v2 + 타입 힌트 완벽 적용

#### 3.1.2 개선 필요 사항
1. **예외 처리 전략 부재**: 글로벌 예외 핸들러 없음
2. **캐싱 미적용**: Redis 설정은 있으나 실제 캐싱 미구현
3. **API 버전 관리**: v1만 존재, 버전 업그레이드 전략 필요

---

### 3.2 설계 검수 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| 기존 프로젝트 패턴과 일관성 | ✅ | 모든 도메인 모듈 동일 구조 |
| 비동기 처리 | ✅ | 모든 DB 작업 async/await |
| N+1 쿼리 방지 | ⚠️ | Eager Loading 메서드 있으나 실제 사용 적음 |
| 트랜잭션 경계 | ✅ | UnitOfWork로 명확하게 관리 |
| 예외 처리 전략 | ❌ | 글로벌 예외 핸들러 필요 |
| 확장성 | ✅ | 모듈 단위 분리로 확장 용이 |
| SOLID 원칙 | ✅ | 대부분 준수 |
| 테스트 가능성 | ⚠️ | 구조는 좋으나 테스트 미작성 |

---

## 4. 리팩토링 우선순위

### 4.1 즉시 수행 (P0)

#### 4.1.1 `.env` 파일 정리
```bash
# 수정 전
DEBU="False"

# 수정 후
DEBUG="False"
```

#### 4.1.2 예외 처리 핸들러 추가
```python
# app/core/exception.py
from fastapi import Request, status
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail

async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# main.py에 등록
app.add_exception_handler(AppException, app_exception_handler)
```

#### 4.1.3 모델 타임존 통일
```python
# app/home/models/models.py:189-193
# 수정 전
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=func.now(),  # DB 서버 시간
    nullable=False,
)

# 수정 후
from config import timezone_settings

created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: timezone_settings.now(),  # 앱 타임존
    nullable=False,
)
```

---

### 4.2 단기 개선 (P1)

#### 4.2.1 Base 모델 통합
```
# 현재 (중복)
app/home/models/base.py
app/user/models/base.py
app/blog/models/base.py
app/sns/models/base.py
app/reply/models/base.py

# 개선
app/database/models/base.py  # 공통 Base, Mixin
app/home/models/models.py    # from app.database.models.base import Base
```

#### 4.2.2 인증 모듈 구현
```python
# app/dependencies/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    # JWT 토큰 검증 로직
    pass
```

#### 4.2.3 Rate Limiting 추가
```python
# main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
```

---

### 4.3 중기 개선 (P2)

#### 4.3.1 Redis 캐싱 구현
```python
# app/database/redis.py
import redis.asyncio as redis
from config import redis_settings

redis_client = redis.from_url(redis_settings.REDIS_URL)

async def get_cached(key: str):
    return await redis_client.get(key)

async def set_cached(key: str, value: str, expire: int = 300):
    await redis_client.set(key, value, ex=expire)
```

#### 4.3.2 테스트 코드 작성
```python
# tests/test_home_api.py
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_get_access_logs():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/home/access-logs")
    assert response.status_code == 200
```

#### 4.3.3 API 문서화 개선
- OpenAPI 스키마에 예제 추가
- 에러 응답 문서화
- API 버전별 문서 분리

---

## 5. 파일별 개선 사항 요약

| 파일 | 개선 사항 | 우선순위 |
|------|----------|----------|
| `.env` | 오타 수정, 보안 강화 | P0 |
| `config.py` | DB 풀 설정 추가, 환경별 분리 | P1 |
| `app/core/exception.py` | 글로벌 예외 핸들러 구현 | P0 |
| `app/database/models/base.py` | 공통 Base 클래스 통합 | P1 |
| `app/dependencies/auth.py` | 인증/인가 로직 구현 | P1 |
| `app/home/models/models.py` | 타임존 설정 통일 | P0 |
| `main.py` | Rate Limiting, 예외 핸들러 등록 | P1 |
| `tests/` | 테스트 코드 작성 | P2 |

---

## 6. 결론

### 6.1 전체 평가
이 프로젝트는 **FastAPI 베스트 프랙티스를 잘 따르고 있으며**, Repository 패턴과 Unit of Work 패턴을 효과적으로 적용했습니다. 코드 가독성과 구조가 우수하며, 확장성을 고려한 설계입니다.

### 6.2 주요 권고사항

1. **즉시 수정 필요**
   - `.env` 파일의 보안 이슈 및 오타 수정
   - 글로벌 예외 처리 핸들러 추가
   - 모델의 타임존 설정 통일

2. **단기 개선**
   - 중복된 `base.py` 파일 통합
   - 인증 모듈 구현
   - Rate Limiting 적용

3. **중기 개선**
   - Redis 캐싱 구현
   - 테스트 코드 작성
   - 모니터링 시스템 연동

### 6.3 예상 효과
- 보안 취약점 제거
- 코드 중복 감소 (약 30%)
- 운영 안정성 향상
- 유지보수성 개선

---

*이 보고서는 코드 리뷰 에이전트와 설계 에이전트의 분석 결과를 통합하여 작성되었습니다.*
