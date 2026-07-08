"""Pagination 데이터클래스 유틸 테스트."""

from app.utils.pagination import Pagination


def test_create_computes_derived_fields():
    """create() 는 total/page_size 로 total_pages·has_next·has_prev 를 계산한다."""
    page = Pagination.create(items=[1, 2, 3], total=25, page=2, page_size=10)
    assert page.items == [1, 2, 3]
    assert page.total == 25
    assert page.page == 2
    assert page.page_size == 10
    assert page.total_pages == 3  # ceil(25/10)
    assert page.has_next is True  # 2 < 3
    assert page.has_prev is True  # 2 > 1


def test_first_page_has_no_prev():
    """첫 페이지는 이전 페이지가 없다."""
    page = Pagination.create(items=["a"], total=5, page=1, page_size=20)
    assert page.total_pages == 1
    assert page.has_prev is False
    assert page.has_next is False


def test_last_page_has_no_next():
    """마지막 페이지는 다음 페이지가 없다."""
    page = Pagination.create(items=[], total=30, page=3, page_size=10)
    assert page.total_pages == 3
    assert page.has_next is False  # 3 < 3 == False
    assert page.has_prev is True


def test_empty_default_instance():
    """모든 필드에 초기값이 있어 인자 없이 '빈 페이지'를 만들 수 있다."""
    page: Pagination[int] = Pagination()
    assert page.items == []
    assert page.total == 0
    assert page.page == 1
    assert page.page_size == 20
    assert page.total_pages == 1
    assert page.has_next is False
    assert page.has_prev is False


def test_mutable_default_is_not_shared():
    """items 는 default_factory 로 정의되어 인스턴스 간 공유되지 않는다(가변 기본값 회피)."""
    a: Pagination[int] = Pagination()
    b: Pagination[int] = Pagination()
    a.items.append(1)
    assert a.items == [1]
    assert b.items == []


def test_zero_total_yields_single_page():
    """total 이 0이어도 total_pages 는 최소 1이다(0 나눗셈 방지)."""
    page = Pagination.create(items=[], total=0, page=1, page_size=20)
    assert page.total_pages == 1
