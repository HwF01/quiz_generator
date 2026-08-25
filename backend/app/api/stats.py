from app.services.quota import remaining
from app.core.deps import get_current_user
from app.core.exceptions import ok
from app.models.user import User
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/quota")
async def quota(user: User = Depends(get_current_user)):
    return ok(await remaining(user.id, user.daily_gen_quota))
