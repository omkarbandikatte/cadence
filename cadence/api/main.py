"""FastAPI app entrypoint. Routers are added milestone by milestone (see docs/08)."""
from __future__ import annotations

from fastapi import FastAPI

from cadence.api.routers import ingest, webhooks

app = FastAPI(title="Cadence", version="0.1.0")
app.include_router(webhooks.router)
app.include_router(ingest.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
