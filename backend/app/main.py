"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.routes import ai, arshin, checks, protocols, reports, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="MKAIR Protocol Control API",
    description="API for controlling calibration protocols of OOO MKAIR",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(arshin.router, prefix="/api/v1/arshin", tags=["arshin"])
app.include_router(protocols.router, prefix="/api/v1/protocols", tags=["protocols"])
app.include_router(checks.router, prefix="/api/v1/checks", tags=["checks"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])


@app.get("/")
async def root():
    return {"message": "MKAIR Protocol Control API", "version": "0.1.0"}
