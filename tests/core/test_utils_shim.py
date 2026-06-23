"""Regression test: old app.utils.* import paths must keep working and
resolve to the same objects as the new app.shared.* canonical paths."""


def test_old_utils_paths_still_import():
    from app.utils.logger import get_logger
    from app.shared.logging import get_logger as new_get
    assert get_logger is new_get


def test_logger_constants_accessible_from_old_path():
    from app.utils.logger import (
        CELERY_LOGGER,
        HOME_LOGGER,
        LYRIC_LOGGER,
        SONG_LOGGER,
        VIDEO_LOGGER,
        APP_LOGGER,
    )
    from app.shared.logging import (
        CELERY_LOGGER as c2,
        HOME_LOGGER as h2,
    )
    assert CELERY_LOGGER == c2
    assert HOME_LOGGER == h2


def test_pagination_shim():
    from app.utils.pagination import PaginatedResponse
    from app.shared.pagination.pagination import PaginatedResponse as PR2
    assert PaginatedResponse is PR2
