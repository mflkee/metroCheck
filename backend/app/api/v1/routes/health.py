"""Health check endpoint."""

from fastapi import APIRouter

from app.services.health_monitor import get_health_monitor

router = APIRouter()


@router.get("/health")
async def health_check():
    """Full system health check."""
    monitor = get_health_monitor()
    health = await monitor.check_all()
    
    # Overall status
    all_ok = all(
        v.get("status") in ["ok", "not_configured"]
        for v in health.values()
        if isinstance(v, dict)
    )
    
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "mkair-backend",
        "systems": health,
    }
