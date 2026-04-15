"""FastAPI entrypoint. Thin routes, all logic in core/services."""
from __future__ import annotations

from fastapi import FastAPI

from backend.routes import actions, ai, analysis, pipeline, portfolio
from db.init_db import init_db
from utils.logging import get_logger

log = get_logger(__name__)

app = FastAPI(title="AI Investment Decision Engine", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    log.info("Backend ready")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
app.include_router(actions.router, prefix="/actions", tags=["actions"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])
