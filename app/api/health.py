"""FastAPI: health/metrics endpoint."""
from __future__ import annotations

from fastapi import FastAPI

from app.bot.handlers import ctx

app = FastAPI(title="Gift Aggregator Bot", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    c = ctx()
    return {
        "status": "ok",
        "sources": [
            {
                "marketplace": a.marketplace.value,
                "status": a.status.value,
                "last_ok_at": a.last_ok_at.isoformat() if a.last_ok_at else None,
                "latency_ms": a.latency_ms,
                "errors_total": a.errors_total,
                "last_error": a.last_error or None,
                "disabled_reason": a.disabled_reason or None,
            }
            for a in c.adapters
        ],
    }


@app.get("/metrics")
async def metrics() -> dict:
    c = ctx()
    return {
        "sources_live": sum(1 for a in c.adapters if a.status.value == "live"),
        "sources_degraded": sum(1 for a in c.adapters if a.status.value == "degraded"),
        "sources_disabled": sum(1 for a in c.adapters if a.status.value == "disabled"),
    }
