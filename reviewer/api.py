import hmac

from fastapi import FastAPI, Header, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from reviewer.config import get_settings
from reviewer.database import engine


def authorize(authorization: str = Header(default="")):
    expected = f"Bearer {get_settings().internal_api_token}"
    if not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(401, "Invalid service credentials")


def headers():
    return {"Authorization": f"Bearer {get_settings().internal_api_token}"}


def make_app(name: str, database: bool = True):
    app = FastAPI(title=f"PR Reviewer · {name}", version="0.1.0")
    Instrumentator().instrument(app).expose(app)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": name}

    @app.get("/ready")
    def ready():
        if database:
            try:
                with engine().connect() as connection:
                    connection.execute(text("SELECT 1"))
            except Exception:
                raise HTTPException(503, "Database unavailable") from None
        return {"status": "ready"}

    return app
