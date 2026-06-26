"""Post Repository — 게시글 데이터 접근.

BaseRepository 의 CRUD 를 그대로 사용한다(특화 쿼리가 필요해지면 여기에 추가).
"""

from app.core.repositories.repository_base import BaseRepository
from app.domains.blog.models.models import Post


class PostRepository(BaseRepository[Post]):
    """게시글 Repository."""

    model = Post
