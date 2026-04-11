from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.db import init_db
from api.app.routes.actions import router as actions_router
from api.app.routes.audit import router as audit_router
from api.app.routes.documents import router as documents_router
from api.app.routes.health import router as health_router
from api.app.routes.settings import router as settings_router


def create_app() -> FastAPI:
    app = FastAPI(title="Local AI Assistant Prototype", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    app.include_router(health_router)
    app.include_router(actions_router)
    app.include_router(audit_router)
    app.include_router(documents_router)
    app.include_router(settings_router)
    return app


app = create_app()
