"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.api.v1.routes import ai, arshin, checks, protocols, reports, health, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.services.job_queue_service import JobQueueService
    from app.services.scheduler_service import SchedulerService
    
    db = AsyncSessionLocal()
    queue_service = JobQueueService(db)
    scheduler_service = SchedulerService(queue_service)
    
    worker_task = asyncio.create_task(queue_service.start_worker())
    scheduler_task = asyncio.create_task(scheduler_service.start())
    
    # Store scheduler in app state for API access
    app.state.scheduler = scheduler_service
    
    yield
    
    # Shutdown
    queue_service.stop_worker()
    scheduler_service.stop()
    
    for task in (worker_task, scheduler_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await db.close()


app = FastAPI(
    title="metroChek Protocol Control API",
    description="API for controlling calibration protocols of OOO metroChek",
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
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])

# Serve static files (UI)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def root():
    return FileResponse("app/static/index.html")
