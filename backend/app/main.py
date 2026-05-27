"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
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
    from app.services.cron_service import CronService
    
    db = AsyncSessionLocal()
    queue_service = JobQueueService(db)
    cron_service = CronService(queue_service)
    
    worker_task = asyncio.create_task(queue_service.start_worker())
    cron_task = asyncio.create_task(cron_service.start())
    
    yield
    
    # Shutdown
    queue_service.stop_worker()
    cron_service.stop()
    
    for task in (worker_task, cron_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await db.close()


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
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])

# Serve static files (UI)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def root():
    return FileResponse("app/static/index.html")
