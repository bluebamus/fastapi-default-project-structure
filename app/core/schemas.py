"""기능 공통 스키마 기반 (service-hardening ADR-008 ①).

부분 수정(PATCH) 요청은 "보낸 필드만 바꾼다" 는 계약이라 모든 필드가 ``X | None = None``
이다. 그 ``None`` 은 "보내지 않음" 의 기본값일 뿐인데, 클라이언트가 ``{"title": null}`` 을
**명시적으로 보내면** 같은 ``None`` 이 ``exclude_unset`` 을 통과해 NOT NULL 컬럼으로
내려가고 DB 가 500 을 냈다. 보낸 필드(``model_fields_set``) 중 값이 None 인데 nullable 로
선언되지 않은 필드는 요청 검증 단계에서 422 로 막는다.
"""

from __future__ import annotations

from typing import ClassVar, Self

from pydantic import BaseModel, model_validator


class PatchSchema(BaseModel):
    """모든 Update 스키마의 기반.

    Attributes:
        nullable_fields: ``null`` 로 비울 수 있는 필드 이름. 모델 컬럼이 nullable 인 필드만
            적는다 — 적지 않은 필드에 ``null`` 을 보내면 422.
    """

    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> Self:
        rejected = sorted(
            name
            for name in self.model_fields_set - self.nullable_fields
            if getattr(self, name) is None
        )
        if rejected:
            raise ValueError(f"null 로 비울 수 없는 필드입니다: {', '.join(rejected)}")
        return self
