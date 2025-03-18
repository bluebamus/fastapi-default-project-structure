import sys
import os
from fastapi.middleware.cors import CORSMiddleware
from app.core.settings import settings
from fastapi import FastAPI

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # root 경로 추가


class CustomCORSMiddleware:
    def __init__(self, app: FastAPI):
        self.app = app

    def configure_cors(self):
        if settings.ENVIRONMENT == "development":
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=settings.CORS_ALLOW_ORIGINS,
                allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
                allow_methods=settings.CORS_ALLOW_METHODS,
                allow_headers=settings.CORS_ALLOW_HEADERS,
                expose_headers=settings.CORS_EXPOSE_HEADERS,
                max_age=settings.CORS_MAX_AGE,
            )
        else:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
