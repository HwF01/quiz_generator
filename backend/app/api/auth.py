import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.acl import LEGACY_SEED_EMAILS, SEED_EMAIL
from app.core.deps import get_current_user
from app.core.exceptions import AppError, ok
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn, UserOut
from app.services.quota import remaining

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(User).where(User.email == body.email))
    if exists.scalar_one_or_none():
        raise AppError("该邮箱已注册")
    user = User(
        email=body.email,
        password_hash=await asyncio.to_thread(hash_password, body.password),
        nickname=body.nickname or body.email.split("@")[0],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(user.id)
    return ok({"token": token, "user": UserOut.model_validate(user).model_dump()})


@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    if body.email.lower() in {SEED_EMAIL, *LEGACY_SEED_EMAILS}:
        raise AppError("系统账号禁止登录", code=401, status_code=401)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise AppError("邮箱或密码错误", code=401, status_code=401)
    token = create_access_token(user.id)
    return ok({"token": token, "user": UserOut.model_validate(user).model_dump()})


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    quota = await remaining(user.id, user.daily_gen_quota)
    data = UserOut.model_validate(user).model_dump()
    data["quota"] = quota
    return ok(data)
