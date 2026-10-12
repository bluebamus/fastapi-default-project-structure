"""update_* 서비스의 no-op PATCH 처리 회귀 테스트 (M4).

MySQL(aiomysql, CLIENT_FOUND_ROWS 미설정)은 동일 값 UPDATE 시 rowcount=0 을 반환한다.
이때 repository.update_by_id 는 None 을 돌려주는데, 서비스는 존재를 이미 확인했으므로 404 가
아니라 현재 엔티티를 반환해야 한다. 테스트 하니스는 SQLite 라 이 조건이 자연 발생하지
않으므로, repository 를 스텁하여 'None 반환(no-op)'과 '부재(get_by_id=None)'를 분리 검증한다.
"""

from types import SimpleNamespace

import pytest

from app.core.exception import NotFoundException
from app.core.security.authorization import OwnershipPolicy
from app.features.blog.schemas.blog_schema import PostUpdate
from app.features.blog.services.blog_service import BlogService
from app.features.reply.schemas.reply_schema import ReplyUpdate
from app.features.reply.services.reply_service import ReplyService
from app.features.sns.schemas.sns_schema import SnsPostUpdate
from app.features.sns.services.sns_service import SnsService
from app.features.user.schemas.user_schema import UserUpdate
from app.features.user.services.user_service import UserService
from tests.auth_headers import SUPERUSER

_POLICY = OwnershipPolicy()

# (서비스 생성 함수, update 메서드명, 부분수정 스키마 인스턴스). DB 없이 구성한다(트랜잭션 경계 불필요).
# user 의 해시기·회전 저장소는 이 경로(활성 유지)에서 쓰이지 않는다.
_CASES = [
    (lambda: BlogService(None, _POLICY), "update_post", PostUpdate(title="unchanged")),
    (lambda: UserService(None, _POLICY, None, None), "update_user", UserUpdate(is_active=True)),
    (lambda: ReplyService(None, _POLICY), "update_reply", ReplyUpdate(content="unchanged")),
    (lambda: SnsService(None, _POLICY), "update_post", SnsPostUpdate(content="unchanged")),
]


class _StubRepo:
    """get_by_id 는 엔티티를, update_by_id 는 None(변경행 0=no-op)을 반환하는 스텁."""

    def __init__(self, entity):
        self.entity = entity

    async def get_by_id(self, _id):
        return self.entity

    async def update_by_id(self, _id, _data):
        return None


class _MissingRepo:
    """get_by_id 가 None(부재)을 반환하는 스텁."""

    async def get_by_id(self, _id):
        return None

    async def update_by_id(self, _id, _data):  # pragma: no cover - 호출 전 404
        return None


def _build(make_service, repo):
    service = make_service()
    service.repository = repo
    return service


@pytest.mark.parametrize("make_service,method,payload", _CASES)
async def test_noop_update_returns_existing_not_404(make_service, method, payload):
    """update 가 None(no-op)이어도 존재하는 엔티티는 404 없이 그대로 반환된다."""
    sentinel = SimpleNamespace(id="x1", author_id=None)
    service = _build(make_service, _StubRepo(sentinel))
    result = await getattr(service, method)("x1", payload, SUPERUSER)
    assert result is sentinel


@pytest.mark.parametrize("make_service,method,payload", _CASES)
async def test_missing_entity_still_raises(make_service, method, payload):
    """실제로 존재하지 않는 엔티티는 여전히 NotFound 예외가 발생한다."""
    service = _build(make_service, _MissingRepo())
    with pytest.raises(NotFoundException):  # 각 도메인의 *NotFoundException 은 이를 상속
        await getattr(service, method)("missing", payload, SUPERUSER)
