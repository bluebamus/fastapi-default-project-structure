# API 설계 예시

## 사용자 관리 API

### 엔드포인트 설계

| Method | Endpoint | 설명 | 인증 |
|--------|----------|------|------|
| POST | `/api/v1/users` | 사용자 생성 | 불필요 |
| GET | `/api/v1/users` | 사용자 목록 조회 | 필요 (Admin) |
| GET | `/api/v1/users/{id}` | 사용자 상세 조회 | 필요 |
| PATCH | `/api/v1/users/{id}` | 사용자 정보 수정 | 필요 (본인/Admin) |
| DELETE | `/api/v1/users/{id}` | 사용자 삭제 (소프트) | 필요 (Admin) |
| POST | `/api/v1/users/{id}/activate` | 사용자 활성화 | 필요 (Admin) |

### 상세 명세

#### `POST /api/v1/users` - 사용자 생성

**요청:**
```json
{
  "email": "user@example.com",
  "password": "securePassword123!",
  "name": "홍길동",
  "phone": "010-1234-5678"
}
```

**성공 응답 (201 Created):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "홍길동",
  "phone": "010-1234-5678",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**에러 응답:**
| 코드 | 상황 | 응답 |
|------|------|------|
| 400 | 잘못된 이메일 형식 | `{"detail": "Invalid email format"}` |
| 409 | 이메일 중복 | `{"detail": "Email already registered"}` |
| 422 | 비밀번호 정책 위반 | `{"detail": "Password must contain..."}` |

#### `GET /api/v1/users` - 목록 조회 (페이지네이션)

**요청 파라미터:**
| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| page | int | N | 1 | 페이지 번호 |
| size | int | N | 20 | 페이지 크기 (max: 100) |
| status | string | N | - | 상태 필터 (active/inactive/pending) |
| search | string | N | - | 이름/이메일 검색 |
| sort | string | N | -created_at | 정렬 (필드명, -는 내림차순) |

**성공 응답 (200 OK):**
```json
{
  "items": [
    {
      "id": 1,
      "email": "user@example.com",
      "name": "홍길동",
      "status": "active",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "size": 20,
    "total_items": 150,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false
  }
}
```

### 페이지네이션 스키마 표준

```python
from pydantic import BaseModel, Field
from typing import Generic, TypeVar

T = TypeVar("T")

class PaginationMeta(BaseModel):
    """페이지네이션 메타 정보"""
    page: int = Field(ge=1, description="현재 페이지")
    size: int = Field(ge=1, le=100, description="페이지 크기")
    total_items: int = Field(ge=0, description="전체 항목 수")
    total_pages: int = Field(ge=0, description="전체 페이지 수")
    has_next: bool = Field(description="다음 페이지 존재 여부")
    has_prev: bool = Field(description="이전 페이지 존재 여부")

class PaginatedResponse(BaseModel, Generic[T]):
    """페이지네이션 응답 래퍼"""
    items: list[T]
    pagination: PaginationMeta
```

### 에러 응답 표준

```python
class ErrorResponse(BaseModel):
    """표준 에러 응답"""
    detail: str = Field(description="에러 메시지")
    code: str | None = Field(default=None, description="에러 코드")
    errors: list[dict] | None = Field(default=None, description="상세 에러 목록")

# 예시: 유효성 검증 에러
{
    "detail": "Validation failed",
    "code": "VALIDATION_ERROR",
    "errors": [
        {"field": "email", "message": "Invalid email format"},
        {"field": "password", "message": "Must be at least 8 characters"}
    ]
}
```
