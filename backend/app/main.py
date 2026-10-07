"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.routes import ai, arshin, auth, checks, protocols, reports, health, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.services.job_queue_service import init_queue_service
    from app.services.scheduler_service import SchedulerService
    
    from app.core.auth import init_admin

    admin_password = init_admin(settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)
    if settings.ADMIN_PASSWORD:
        logger.info("Admin credentials configured via environment: %s", settings.ADMIN_USERNAME)
    else:
        logger.info("=" * 60)
        logger.info("  AUTH: Admin user:     %s", settings.ADMIN_USERNAME)
        logger.info("  AUTH: Admin password:  %s", admin_password)
        logger.info("  AUTH: Save this password — it won't be shown again")
        logger.info("=" * 60)

    db = AsyncSessionLocal()
    
    # Recover orphaned jobs after restart
    from app.models.job import Job
    from sqlalchemy import select
    async with db.begin():
        result = await db.execute(select(Job).where(Job.status == "running"))
        for job in result.scalars().all():
            job.status = "failed"
            job.progress = "Прервано перезапуском сервера"
            job.progress_percent = 0
            logger.info("Recovered orphaned job #%s", job.id)
    
    queue_service = init_queue_service(db)
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
app.include_router(auth.router)
app.include_router(health.router, tags=["health"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(arshin.router, prefix="/api/v1/arshin", tags=["arshin"])
app.include_router(protocols.router, prefix="/api/v1/protocols", tags=["protocols"])
app.include_router(checks.router, prefix="/api/v1/checks", tags=["checks"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
