from fastapi import APIRouter, Depends

from app.db import AsyncSession, get_db
from app.models.admin import AdminDetails
from app.models.auto_setup import SmartSetupRequest, SmartSetupResponse
from app.operation.auto_setup import smart_setup_operator
from app.utils import responses

from .authentication import require_permission

router = APIRouter(
    tags=["Smart Setup"],
    prefix="/api/smart_setup",
    responses={401: responses._401, 403: responses._403},
)


@router.post("", response_model=SmartSetupResponse)
async def run_smart_setup(
    request: SmartSetupRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminDetails = Depends(require_permission("cores", "create")),
):
    """One-shot secure stack: measures latency, picks a profile, generates a
    REALITY keypair and creates the core config + group + hosts."""
    return await smart_setup_operator.run_setup(db, request, admin)
