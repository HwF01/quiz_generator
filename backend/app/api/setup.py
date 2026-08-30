from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.core.exceptions import ok
from app.core.setup_config import apply_setup_update, setup_status
from app.models.user import User
from app.schemas.setup import SetupUpdate

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("")
async def get_setup():
    return ok(setup_status())


@router.put("")
async def put_setup(body: SetupUpdate, _user: User = Depends(get_current_user)):
    data = apply_setup_update(
        qwen_api_key=body.qwen_api_key,
        deepseek_api_key=body.deepseek_api_key,
        tavily_api_key=body.tavily_api_key,
        use_demo=body.use_demo,
        clear_tavily=body.clear_tavily,
    )
    return ok(data)
