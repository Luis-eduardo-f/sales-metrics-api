"""FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload

Interactive API docs are served at /docs (Swagger UI) and /redoc.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.database import init_db
from app.routers import customers, health, metrics

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Ensure tables exist. In this demo project this replaces a migration tool; see README.
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "A FastAPI service that serves analytical metrics (revenue over time, top products, "
        "customer summaries) over a synthetic sales dataset. Protected endpoints require an "
        "`X-API-Key` header -- see the README for setup instructions."
    ),
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(customers.router)
