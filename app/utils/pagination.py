# Shim: re-exports everything from the new canonical location.
# Old importers using `app.utils.pagination` continue to work unchanged.
from app.shared.pagination.pagination import *   # noqa: F401,F403
