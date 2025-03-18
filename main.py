from fastapi import FastAPI
from core.settings import ENV_PATH, settings
from app.core.database import engine
from app.core.database import Base
from app.core.middleware import CustomCORSMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
)

Base.metadata.create_all(engine)  # Create tables

# Create an instance of your custom CORS middleware
custom_cors_middleware = CustomCORSMiddleware(app)

# Configure CORS middleware based on environment
custom_cors_middleware.configure_cors()

