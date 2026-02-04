# 보안 체크리스트

## OWASP Top 10 (2021) 기반

### A01: Broken Access Control

#### 체크 항목
- [ ] 모든 엔드포인트에 인증 적용 여부
- [ ] 리소스 접근 시 소유권 검증
- [ ] 관리자 기능 권한 분리
- [ ] JWT 토큰 검증 로직
- [ ] CORS 설정 적절성

#### 취약 패턴
```python
# ❌ IDOR (Insecure Direct Object Reference)
@router.get("/orders/{order_id}")
async def get_order(order_id: int):
    return await service.get_order(order_id)  # 누구든 접근 가능!

# ✅ 수정
@router.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user)
):
    order = await service.get_order(order_id)
    if order.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    return order
```

---

### A02: Cryptographic Failures

#### 체크 항목
- [ ] 비밀번호 해싱 알고리즘 (bcrypt/argon2)
- [ ] 민감 데이터 암호화 (at-rest, in-transit)
- [ ] 시크릿 키 환경변수 관리
- [ ] HTTPS 강제 적용

#### 취약 패턴
```python
# ❌ 평문 비밀번호 저장
user.password = request.password

# ✅ 해싱 적용
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"])
user.password_hash = pwd_context.hash(request.password)
```

---

### A03: Injection

#### 체크 항목
- [ ] SQL Injection 방어 (ORM 파라미터 바인딩)
- [ ] Command Injection 방어
- [ ] NoSQL Injection 방어
- [ ] XSS 방어 (출력 이스케이핑)

#### 취약 패턴
```python
# ❌ SQL Injection
query = f"SELECT * FROM users WHERE name = '{name}'"
await session.execute(text(query))

# ✅ 파라미터 바인딩
stmt = select(User).where(User.name == name)
await session.execute(stmt)

# ❌ Command Injection
os.system(f"convert {filename}")

# ✅ 안전한 처리
import shlex
subprocess.run(["convert", shlex.quote(filename)])
```

---

### A04: Insecure Design

#### 체크 항목
- [ ] 비즈니스 로직 검증 (잔액 체크, 재고 체크 등)
- [ ] Rate Limiting 적용
- [ ] 과도한 데이터 노출 방지
- [ ] 실패 시나리오 처리

#### 취약 패턴
```python
# ❌ 비즈니스 로직 검증 누락
async def transfer(from_id: int, to_id: int, amount: Decimal):
    await decrease_balance(from_id, amount)
    await increase_balance(to_id, amount)

# ✅ 검증 추가
async def transfer(from_id: int, to_id: int, amount: Decimal):
    if amount <= 0:
        raise ValidationError("Amount must be positive")

    balance = await get_balance(from_id)
    if balance < amount:
        raise ValidationError("Insufficient balance")

    async with transaction():
        await decrease_balance(from_id, amount)
        await increase_balance(to_id, amount)
```

---

### A05: Security Misconfiguration

#### 체크 항목
- [ ] 디버그 모드 비활성화 (프로덕션)
- [ ] 불필요한 기능 비활성화
- [ ] 에러 메시지 정보 노출
- [ ] 기본 계정/비밀번호 변경

#### 취약 패턴
```python
# ❌ 프로덕션 디버그 모드
app = FastAPI(debug=True)

# ✅ 환경별 설정
app = FastAPI(debug=settings.DEBUG)

# ❌ 상세 에러 노출
except Exception as e:
    return {"error": str(e), "traceback": traceback.format_exc()}

# ✅ 안전한 에러 처리
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    return {"error": "Internal server error"}
```

---

### A06: Vulnerable Components

#### 체크 항목
- [ ] 의존성 취약점 스캔 (pip-audit, safety)
- [ ] 정기적 업데이트 정책
- [ ] 사용하지 않는 의존성 제거

```bash
# 취약점 스캔
pip-audit
safety check
```

---

### A07: Authentication Failures

#### 체크 항목
- [ ] 강력한 비밀번호 정책
- [ ] 계정 잠금 정책 (brute force 방지)
- [ ] 세션 관리 (만료, 무효화)
- [ ] MFA 지원

#### 취약 패턴
```python
# ❌ 약한 비밀번호 허용
if len(password) >= 4:
    pass

# ✅ 강력한 정책
import re
def validate_password(password: str) -> bool:
    if len(password) < 12:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*]", password):
        return False
    return True
```

---

### A08: Software and Data Integrity Failures

#### 체크 항목
- [ ] 서명된 패키지만 사용
- [ ] CI/CD 파이프라인 보안
- [ ] 데이터 무결성 검증

---

### A09: Security Logging and Monitoring

#### 체크 항목
- [ ] 인증 실패 로깅
- [ ] 권한 위반 로깅
- [ ] 중요 작업 감사 로그
- [ ] 로그 모니터링/알림

```python
# ✅ 보안 이벤트 로깅
logger.warning(
    "Authentication failed",
    extra={
        "event": "auth_failure",
        "email": email,
        "ip": request.client.host,
        "user_agent": request.headers.get("user-agent")
    }
)
```

---

### A10: Server-Side Request Forgery (SSRF)

#### 체크 항목
- [ ] 사용자 입력 URL 검증
- [ ] 화이트리스트 기반 URL 필터링
- [ ] 내부 네트워크 접근 차단

```python
# ❌ SSRF 취약
async def fetch_url(url: str):
    return await httpx.get(url)

# ✅ URL 검증
from urllib.parse import urlparse

ALLOWED_HOSTS = {"api.example.com", "cdn.example.com"}

async def fetch_url(url: str):
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValidationError("URL not allowed")
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Invalid scheme")
    return await httpx.get(url)
```
