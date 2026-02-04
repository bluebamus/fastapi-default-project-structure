from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import cors_settings

# sys.path.append(
#     os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# )  # root 경로 추가


class CustomCORSMiddleware:
    def __init__(self, app: FastAPI):
        self.app = app

    def configure_cors(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_settings.CORS_ALLOW_ORIGINS,
            allow_credentials=cors_settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=cors_settings.CORS_ALLOW_METHODS,
            allow_headers=cors_settings.CORS_ALLOW_HEADERS,
            expose_headers=cors_settings.CORS_EXPOSE_HEADERS,
            max_age=cors_settings.CORS_MAX_AGE,
        )
