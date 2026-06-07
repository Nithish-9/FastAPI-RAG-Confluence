from core.state import system_state
from fastapi import HTTPException

async def require_workspace_ready() -> None:
    if not system_state.is_system_ready():
        raise HTTPException(status_code=503, detail="Infrastructure not ready. Retry shortly.")
    if not await system_state.is_workspace_queue_healthy():
        raise HTTPException(status_code=429, detail="Workspace queues saturated. Retry shortly.")

async def require_enterprise_ready() -> None:
    if not system_state.is_system_ready():
        raise HTTPException(status_code=503, detail="Infrastructure not ready. Retry shortly.")
    if not await system_state.is_enterprise_queue_healthy():
        raise HTTPException(status_code=429, detail="Enterprise queues saturated. Retry shortly.")