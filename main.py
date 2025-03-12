from fastapi import FastAPI
from core.settings import ENV_PATH, settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
)