"""FastAPI app entrypoint. Routers are added milestone by milestone (see docs/08)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cadence.api.routers import actions, ingest, reads, sim, webhooks

app = FastAPI(title="Cadence", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhooks.router)
app.include_router(ingest.router)
app.include_router(reads.router)
app.include_router(actions.router)
app.include_router(sim.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
