"""FastAPI app entrypoint. Routers are added milestone by milestone (see docs/08)."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Cadence", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
