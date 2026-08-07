from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.routers.categories import router as categories_router
from app.services.categories import seed_default_categories


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Alembic is used for managed upgrades; create_all keeps first-run local setup frictionless.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_default_categories(session)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(categories_router, prefix=settings.api_prefix)


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
