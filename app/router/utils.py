from core.state import system_state
from fastapi import HTTPException

def require_system_ready():
    if not system_state.is_system_ready():
        raise HTTPException(
            status_code=503,
            detail="Search infrastructure is not fully ready. Retry shortly.",
        )