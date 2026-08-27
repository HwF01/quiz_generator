import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import AppError, ok
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.services.storage import upload_bytes

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(f"文件不能超过 {settings.max_upload_mb}MB")
    name = file.filename or "upload.bin"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in set(ALLOWED.values()):
        raise AppError("仅支持 PDF / Word / PPT / TXT")
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if ctype not in ALLOWED:
        raise AppError("文件类型不被支持")
    if ALLOWED[ctype] != ext:
        raise AppError("文件扩展名与类型不一致")
    key = f"{user.id}/{uuid4()}{ext}"
    try:
        await asyncio.to_thread(upload_bytes, key, data, ctype)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("文件保存失败，请稍后重试", code=503, status_code=503) from exc
    doc = Document(
        owner_id=user.id,
        filename=name,
        content_type=file.content_type or "application/octet-stream",
        object_key=key,
        size_bytes=len(data),
        status="uploaded",
    )
    try:
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("保存文档失败，请稍后重试", code=500, status_code=500) from exc
    return ok({"id": doc.id, "filename": doc.filename, "size_bytes": doc.size_bytes})
