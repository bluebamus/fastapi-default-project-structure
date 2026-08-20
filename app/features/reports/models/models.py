"""Reports 도메인 데이터베이스 모델 — Raw SQL 의 **원본 테이블**만 정의한다.

집계 결과용 ORM 모델은 만들지 않는다(SCN-RAW-001). 일별 매출 집계는 행 하나가
테이블의 행이 아니라 계산 결과이므로, ``RowMapping`` → Pydantic DTO 로 나간다.

그렇다면 왜 ``SalesOrder`` 는 있는가:
    이 테이블의 **생명주기를 이 프로젝트가 소유**하기 때문이다. migration 으로
    만들고 지우는 테이블이라면 metadata 에 있어야 Alembic 이 드리프트를 볼 수 있다
    (지침서 §2 의 단서). 모델이 없으면 ``compare_metadata`` 가 이 테이블을
    "지워야 할 것"으로 판정한다.

    ``sales_orders`` 에 대한 쓰기는 이 예제 범위가 아니다 — 원장은 migration/fixture
    로 채우고, 읽기는 Raw 집계로 한다.

Raw **쓰기** 예제는 ``SalesDailySnapshot`` 이 맡는다:
    원장을 고치는 것이 아니라 **집계 결과를 다른 테이블에 적재**한다. 원장 불변성을
    지키면서 Raw DML(``INSERT ... SELECT``)의 워크플로를 보여주는 자리다(SCN-RAW-003).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.models_base import Base, UUIDCreatedModel


class SalesOrder(UUIDCreatedModel):
    """주문 원장 — 일별 매출 집계의 원본.

    생성 후 변하지 않는 기록이라 ``updated_at`` 을 두지 않는다(UUIDCreatedModel).

    Attributes:
        id: UUID 기본키 (UUIDPrimaryKeyMixin)
        customer: 주문 고객 식별자
        total_amount: 주문 총액
        created_at: 주문 시각 — 집계의 기준 (CreatedAtMixin)
    """

    __tablename__ = "sales_orders"

    # 일별 집계는 created_at 범위로 스캔한다. 인덱스가 없으면 전체 스캔이 된다(NFR-002).
    # created_at 은 Mixin 이 제공하므로 컬럼 인자가 아니라 __table_args__ 로 건다.
    __table_args__ = (Index("ix_sales_orders_created_at", "created_at"),)

    customer: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="주문 고객 식별자",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="주문 총액",
    )

    def __repr__(self) -> str:
        return f"<SalesOrder(id={self.id}, customer={self.customer!r})>"


class SalesDailySnapshot(Base):
    """일별 매출 스냅샷 — Raw ``INSERT ... SELECT`` 로 적재되는 집계 결과.

    왜 UUID 기본키가 아닌가:
        이 테이블의 행은 "하루" 다. 하루는 그 자체로 유일하므로 ``sales_date`` 가
        자연키다. 대리키를 얹으면 "같은 날짜가 두 줄" 인 상태가 표현 가능해지고,
        그러면 리포트가 두 배로 보이는 사고를 스키마가 막아주지 못한다.

    왜 ``DailySalesItem`` 처럼 DTO 로 끝내지 않는가:
        읽기 전용 집계는 계산 결과라 테이블이 필요 없다(SCN-RAW-001). 반면 스냅샷은
        **적재해서 남기는 것**이 목적이라 생명주기를 이 프로젝트가 소유한다. 소유하면
        모델이 있어야 Alembic 이 드리프트를 본다.

    갱신 컬럼(``generated_at``)에 관하여:
        Mixin 의 ``default``/``onupdate`` 는 ORM/Core 가 발행하는 문장에서만 동작한다.
        이 테이블은 Raw DML 로 채우므로 값을 **SQL 의 바인드 파라미터로 명시**한다
        (``models_base.UpdatedAtMixin`` 의 단서). Mixin 을 쓰면 조용히 NULL 이 된다.

    Attributes:
        sales_date: 매출 일자 — 자연 기본키
        order_count: 그날의 주문 수
        gross_amount: 그날의 총 매출
        generated_at: 이 행을 적재한 시각 — 리포트의 신선도 판단 근거
    """

    __tablename__ = "sales_daily_snapshots"

    # 스냅샷은 보통 "최근 적재분" 을 훑는다. 신선도 조회가 전체 스캔이 되지 않게 한다.
    __table_args__ = (Index("ix_sales_daily_snapshots_generated_at", "generated_at"),)

    sales_date: Mapped[date] = mapped_column(
        Date(),
        primary_key=True,
        comment="매출 일자 (자연 기본키)",
    )
    order_count: Mapped[int] = mapped_column(
        nullable=False,
        comment="그날의 주문 수",
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        comment="그날의 총 매출",
    )
    generated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        comment="적재 시각 — Raw DML 이 바인드 파라미터로 채운다",
    )

    def __repr__(self) -> str:
        return f"<SalesDailySnapshot(sales_date={self.sales_date}, count={self.order_count})>"
