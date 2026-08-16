"""FastAPI app factory. Routes are thin — every response is built from
service.py / config.py, the same functions the CLI calls. Nothing here
reimplements lock/generate/verify/amend logic.
"""

from __future__ import annotations

from fastapi import FastAPI

from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Policy Pack Localizer",
        description="Field-office policy pack localizer, built on SuperDocs.",
    )
    app.include_router(router)
    return app


app = create_app()
