"""FastAPI 진입점. 모든 조립은 create_app() 안에서 수행한다(app/apps.py 등록 기반)."""
from app.core.bootstrap import create_app
from config import app_settings

app = create_app()

if __name__ == "__main__":
    import uvicorn
    from app.utils.logs import setup_uvicorn_logging
    uvicorn.run("main:app", host="0.0.0.0", port=8000,
                reload=app_settings.DEBUG, log_config=setup_uvicorn_logging())
