"""관리 화면(/admin) 서버 세션과 CSRF — admin-session-hardening ADR-001~004.

세션 (ADR-001·002):
    쿠키 ``admin_session`` 에는 무작위 세션 ID(``secrets.token_urlsafe(32)``)만 있고, 내용은 Redis 에 있다.

    - ``admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}`` → JSON ``{"data", "user_id", "created_at"}``.
      키가 유출돼도 쿠키(sid)를 만들 수 없고, ``SESSION_SECRET_KEY`` 를 바꾸면 모든 관리 세션이 무효가 된다.
    - ``admin:user_sessions:{user_id}`` → 그 사용자의 세션 키 집합(SET, TTL = 절대 만료). 사용자 단위 폐기용.
    - 만료: 절대 만료(생성 시각 + ``ADMIN_SESSION_MAX_AGE_SECONDS``, 연장 불가) + 미사용 만료
      (``ADMIN_SESSION_IDLE_SECONDS``, 요청마다 TTL 을 다시 잡되 절대 만료를 넘지 않게).
    - ``RedisSessionMiddleware`` 가 ``scope["session"]`` 에 dict 를 넣어 ``request.session`` 인터페이스를
      그대로 쓴다. 세션이 비면 Redis 키를 지우고 쿠키도 지운다. 로그인 성공은 ``rotate_session`` 으로
      새 sid 발급 + 이전 키 삭제를 요청한다(세션 고정 방지).
    - Redis 장애는 fail-closed — 503 을 내고 요청을 통과시키지 않는다.

CSRF (ADR-003·004):
    synchronizer token. 세션의 ``csrf_token`` 과 요청의 토큰(헤더 ``X-CSRF-Token`` 또는 폼 필드
    ``csrf_token``)을 ``hmac.compare_digest`` 로 대조한다. ``AdminCsrfMiddleware`` 가 ``/admin`` 의
    POST·PUT·PATCH·DELETE 전부(로그인·로그아웃 포함)를 검사한다. 폼 본문은 버퍼링해 읽고 같은 바이트를
    다운스트림에 다시 흘려 준다.

sqladmin 을 import 하지 않는다 — user 기능의 폐기 훅이 ``ADMIN_DISABLED=true`` 에서도 가볍게 import 한다.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import HTTPConnection, Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exception import ServiceUnavailableException
from app.utils.logs import get_logger

logger = get_logger("admin_session")

# 기존 세션 쿠키(SESSION_COOKIE_NAME, 기본 "session")와 겹치지 않는 이름.
ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_COOKIE_PATH = "/admin"
SESSION_USER_KEY = "user_id"
SESSION_KEY_PREFIX = "admin:sess:"
USER_INDEX_PREFIX = "admin:user_sessions:"

CSRF_SESSION_KEY = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# ponytail: 토큰을 찾으려고 버퍼링하는 폼 본문 상한. 관리 화면에 파일 업로드(import 등)를 켜서 넘치면 올린다.
MAX_FORM_BODY_BYTES = 10 * 1024 * 1024
# 폼 필드 하나(이름+값, multipart 는 파일 아닌 파트)의 상한 — Starlette 기본값과 같지만 명시해 둔다. 넘으면 400.
MAX_FORM_FIELD_BYTES = 1024 * 1024

STORE_UNAVAILABLE_MESSAGE = "관리 세션 저장소를 사용할 수 없습니다. 잠시 후 다시 시도하세요."
_UNAVAILABLE = (RedisError, ServiceUnavailableException, OSError)
_ROTATE_SCOPE_KEY = "admin_session.rotate"
_STORE_SCOPE_KEY = "admin_session.store"


@dataclass(frozen=True)
class SessionRecord:
    """Redis 에서 읽은 세션 하나."""

    data: dict[str, Any]
    created_at: float


class AdminSessionStore:
    """관리 세션의 Redis 저장·조회·삭제·사용자 단위 폐기."""

    def __init__(
        self,
        redis: Redis,
        *,
        secret_key: str,
        max_age_seconds: int,
        idle_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """
        Args:
            redis: lifespan 이 연 클라이언트.
            secret_key: 세션 ID → Redis 키 HMAC 키(``SESSION_SECRET_KEY``).
            max_age_seconds: 절대 만료(초) — 쿠키 Max-Age 도 이 값.
            idle_seconds: 미사용 만료(초).
            clock: epoch 초(테스트가 시계를 옮긴다).
        """
        self._redis = redis
        self._secret = secret_key.encode()
        self.max_age = max_age_seconds
        self.idle = idle_seconds
        self._clock = clock

    @property
    def redis(self) -> Redis:
        """이 저장소의 Redis — 관리 화면의 폐기 훅이 같은 Redis 로 refresh 저장소를 만든다."""
        return self._redis

    @staticmethod
    def new_session_id() -> str:
        return secrets.token_urlsafe(32)

    def now(self) -> float:
        return self._clock()

    def key(self, sid: str) -> str:
        digest = hmac.new(self._secret, sid.encode(), hashlib.sha256).hexdigest()
        return f"{SESSION_KEY_PREFIX}{digest}"

    @staticmethod
    def user_index_key(user_id: str) -> str:
        return f"{USER_INDEX_PREFIX}{user_id}"

    async def load(self, sid: str) -> SessionRecord | None:
        """sid 의 세션. 없거나(만료·폐기) 절대 만료가 지났으면 ``None``."""
        raw = await self._redis.get(self.key(sid))
        if raw is None:
            return None
        record = json.loads(raw)
        created_at = float(record["created_at"])
        if self.now() >= created_at + self.max_age:
            await self._redis.delete(self.key(sid))
            return None
        return SessionRecord(dict(record["data"]), created_at)

    async def save(
        self, sid: str, data: dict[str, Any], created_at: float, *, new: bool = False
    ) -> bool:
        """저장하고 미사용 TTL 을 다시 잡는다(절대 만료 이내).

        기존 세션(``new=False``)은 키가 아직 있을 때만 쓴다(``SET XX``) — 요청 처리 중에 폐기된 세션을
        응답 저장이 되살리지 않게 한다. 절대 만료가 지났거나 키가 사라졌으면 ``False``.
        """
        key = self.key(sid)
        ttl = min(self.idle, int(created_at + self.max_age - self.now()))
        if ttl <= 0:
            await self._redis.delete(key)
            return False
        user_id = data.get(SESSION_USER_KEY)
        value = json.dumps({"data": data, "user_id": user_id, "created_at": created_at})
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, value, ex=ttl, nx=new, xx=not new)
            if isinstance(user_id, str):
                pipe.sadd(self.user_index_key(user_id), key)
                pipe.expire(self.user_index_key(user_id), self.max_age)
            results = await pipe.execute()
        return bool(results[0])

    async def delete(self, sid: str, data: dict[str, Any]) -> None:
        """세션 하나를 지우고 사용자 인덱스에서도 뺀다(로그아웃·회전)."""
        key = self.key(sid)
        user_id = data.get(SESSION_USER_KEY)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if isinstance(user_id, str):
                pipe.srem(self.user_index_key(user_id), key)
            await pipe.execute()

    async def revoke_user(self, user_id: str) -> int:
        """그 사용자의 관리 세션을 모두 지운다(강등·비활성화·삭제). 지운 세션 수."""
        index = self.user_index_key(user_id)
        # redis-py 의 타입은 동기·비동기 클라이언트를 한 시그니처로 적어 반환형이 합집합이다.
        keys = await cast("Awaitable[set[Any]]", self._redis.smembers(index))
        async with self._redis.pipeline(transaction=True) as pipe:
            for key in keys:
                pipe.delete(key)
            pipe.delete(index)
            results = await pipe.execute()
        return sum(int(n) for n in results[:-1])


def rotate_session(request: HTTPConnection) -> None:
    """이번 응답에서 새 sid 를 발급하고 이전 키를 지우라고 미들웨어에 알린다(로그인 성공)."""
    request.scope[_ROTATE_SCOPE_KEY] = True


def request_session_store(request: HTTPConnection) -> AdminSessionStore:
    """이 관리 요청의 세션 저장소(``RedisSessionMiddleware`` 가 넣는다) — 관리 화면 안의 폐기 훅용."""
    store = request.scope.get(_STORE_SCOPE_KEY)
    if not isinstance(store, AdminSessionStore):
        raise RuntimeError("RedisSessionMiddleware 밖의 요청입니다.")
    return store


class RedisSessionMiddleware:
    """``scope["session"]`` 을 Redis 서버 세션으로 채우고 응답 시작 때 저장·쿠키를 처리한다."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        store_factory: Callable[[], AdminSessionStore],
        https_only: bool,
        cookie_name: str = ADMIN_SESSION_COOKIE,
        path: str = ADMIN_COOKIE_PATH,
    ) -> None:
        """
        Args:
            store_factory: 요청마다 저장소를 만든다 — Redis 는 lifespan 이 연 뒤에야 있다.
            https_only: 쿠키에 ``Secure`` 를 붙일지(staging/production).
        """
        self.app = app
        self._store_factory = store_factory
        self._cookie_name = cookie_name
        self._path = path
        self._secure = "; Secure" if https_only else ""

    def _cookie(self, value: str, max_age: int) -> str:
        return (
            f"{self._cookie_name}={value}; Path={self._path}; Max-Age={max_age}; "
            f"HttpOnly; SameSite=Strict{self._secure}"
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sid = HTTPConnection(scope).cookies.get(self._cookie_name) or None
        try:
            store = self._store_factory()
            record = await store.load(sid) if sid else None
        except _UNAVAILABLE:
            await self._unavailable(scope, receive, send)
            return
        scope["session"] = dict(record.data) if record else {}
        scope[_STORE_SCOPE_KEY] = store
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                cookie = await self._commit(store, scope, sid, record)
                if cookie is not None:
                    MutableHeaders(scope=message).append("set-cookie", cookie)
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except _UNAVAILABLE:
            if started:
                raise
            await self._unavailable(scope, receive, send)

    async def _commit(
        self, store: AdminSessionStore, scope: Scope, sid: str | None, record: SessionRecord | None
    ) -> str | None:
        """세션을 저장하고 내려 보낼 Set-Cookie 값을 돌려준다(없으면 ``None``)."""
        data: dict[str, Any] = scope["session"]
        rotate = bool(scope.get(_ROTATE_SCOPE_KEY))
        if sid is not None and record is not None and (rotate or not data):
            await store.delete(sid, record.data)
        if not data:
            return self._cookie("", 0) if sid is not None else None
        if sid is None or record is None or rotate:
            new_sid = store.new_session_id()
            await store.save(new_sid, data, store.now(), new=True)
            return self._cookie(new_sid, store.max_age)
        if await store.save(sid, data, record.created_at):
            return None
        return self._cookie("", 0)

    @staticmethod
    async def _unavailable(scope: Scope, receive: Receive, send: Send) -> None:
        logger.error("[admin] 관리 세션 저장소(Redis) 장애 — 503", exc_info=True)
        response = PlainTextResponse(STORE_UNAVAILABLE_MESSAGE, status_code=503)
        await response(scope, receive, send)


# =============================================================================
# CSRF
# =============================================================================
def csrf_token(request: HTTPConnection) -> str:
    """관리 세션의 CSRF 토큰 — 없으면 만들어 세션에 둔다(템플릿 전역 ``csrf_token(request)``)."""
    token = request.session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def csrf_valid(request: HTTPConnection, submitted: object) -> bool:
    """세션 토큰과 제출 토큰을 상수 시간으로 대조한다. 어느 쪽이든 없으면 거부."""
    expected = request.session.get(CSRF_SESSION_KEY)
    if not isinstance(expected, str) or not isinstance(submitted, str):
        return False
    # str 의 compare_digest 는 비ASCII 에서 TypeError 라 bytes 로 비교한다.
    return hmac.compare_digest(expected.encode(), submitted.encode())


class _BodyTooLarge(Exception):
    pass


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_FORM_BODY_BYTES:
            raise _BodyTooLarge
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes, receive: Receive) -> Receive:
    """버퍼링한 본문을 한 번 흘려 주고, 그 뒤로는 원래 receive(연결 끊김 등)로 넘긴다."""
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


class AdminCsrfMiddleware:
    """``/admin`` 의 상태 변경 요청(POST·PUT·PATCH·DELETE)마다 CSRF 토큰을 대조한다.

    ``RedisSessionMiddleware`` 안쪽에 둔다(세션이 먼저 있어야 한다). 거부 응답은 주입받은 ``reject`` 가
    그린다 — 로그인 POST 는 로그인 화면, 그 밖은 관리 화면의 오류 화면(403).
    """

    def __init__(self, app: ASGIApp, *, reject: Callable[[Request], Awaitable[Response]]) -> None:
        self.app = app
        self._reject = reject

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        submitted: str | None = request.headers.get(CSRF_HEADER)
        content_type = request.headers.get("content-type", "")
        # 세션 토큰이 없으면 본문을 읽을 것도 없이 거부한다(익명 요청이 본문을 버퍼링시키지 못하게).
        if (
            submitted is None
            and CSRF_SESSION_KEY in request.session
            and content_type.startswith(
                ("application/x-www-form-urlencoded", "multipart/form-data")
            )
        ):
            # 413 판정은 Content-Length 로 먼저(읽지 않고), 없거나 거짓이면 읽는 도중 누적 크기로 (integration-e2e ADR-015).
            declared = request.headers.get("content-length", "")
            try:
                if declared.isdigit() and int(declared) > MAX_FORM_BODY_BYTES:
                    raise _BodyTooLarge
                body = await _read_body(receive)
            except _BodyTooLarge:
                await PlainTextResponse("요청 본문이 너무 큽니다.", status_code=413)(
                    scope, receive, send
                )
                return
            original = receive
            receive = _replay(body, original)  # 다운스트림(sqladmin)이 같은 본문을 다시 읽는다
            request = Request(scope, _replay(body, original))
            try:
                async with request.form(max_part_size=MAX_FORM_FIELD_BYTES) as form:
                    value = form.get(CSRF_FORM_FIELD)
                    submitted = value if isinstance(value, str) else None
            except (
                HTTPException
            ) as exc:  # 필드 1 MiB 초과·깨진 multipart — 400 (integration-e2e ADR-015)
                await PlainTextResponse(
                    "요청 폼이 올바르지 않거나 필드가 너무 큽니다.", status_code=exc.status_code
                )(scope, receive, send)
                return
        if not csrf_valid(request, submitted):
            logger.warning(
                "[admin] CSRF 토큰 불일치: %s %s", scope["method"], request.url.path[:128]
            )
            response = await self._reject(request)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
