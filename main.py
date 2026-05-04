"""
main.py
FastAPI application entry-point for StreamVault.

Routes
------
GET  /                  → gallery of all videos
GET  /upload            → upload form
POST /upload            → handle video upload → S3 + DB background task
GET  /video/{id}        → video detail / player page (presigned URL)
POST /video/{id}/delete → remove video from S3 + DB
GET  /health            → liveness probe
"""

from __future__ import annotations

import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db, init_db
from models import Video
import s3_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Application lifecycle ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("StreamVault started — DB tables ready.")
    yield
    logger.info("StreamVault shutting down.")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── Template helpers ───────────────────────────────────────────────────────────

def _base_ctx(request: Request) -> dict:
    return {"request": request, "app_name": settings.APP_NAME}


# ── Background task ────────────────────────────────────────────────────────────

async def _log_upload_to_db(
    video_id: str,
    title: str,
    description: str | None,
    s3_key: str,
    original_filename: str,
    content_type: str,
    file_size_bytes: int,
) -> None:
    """
    Runs **after** the HTTP response is sent.
    Persists upload metadata to the database.
    """
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        video = Video(
            id=video_id,
            title=title,
            description=description or None,
            s3_key=s3_key,
            original_filename=original_filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
        )
        session.add(video)
        await session.commit()
        logger.info("DB: logged video %s (%s)", video_id, title)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video).order_by(Video.uploaded_at.desc())
    )
    videos = result.scalars().all()

    # Attach a short-lived presigned thumbnail/poster if you have thumbnails,
    # otherwise leave thumbnail_url as None and the template uses a placeholder.
    video_data = []
    for v in videos:
        thumb_url = None
        if v.thumbnail_s3_key:
            try:
                thumb_url = s3_service.generate_presigned_url(v.thumbnail_s3_key, expiry=3600)
            except RuntimeError:
                pass
        video_data.append({"video": v, "thumb_url": thumb_url})

    ctx = _base_ctx(request)
    ctx["video_data"] = video_data
    ctx["total_videos"] = len(videos)
    return templates.TemplateResponse("index.html", ctx)


@app.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request):
    ctx = _base_ctx(request)
    ctx["max_size_mb"] = settings.MAX_UPLOAD_SIZE_MB
    return templates.TemplateResponse("upload.html", ctx)


@app.post("/upload", response_class=HTMLResponse)
async def upload_video(
    request: Request,
    background_tasks: BackgroundTasks,
    title: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    video_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # ── Basic validation ───────────────────────────────────────────────────────
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    allowed_mime_prefixes = ("video/",)

    content_type = video_file.content_type or s3_service.guess_content_type(
        video_file.filename or "video.mp4"
    )

    if not any(content_type.startswith(p) for p in allowed_mime_prefixes):
        ctx = _base_ctx(request)
        ctx["error"] = f"Only video files are accepted (got '{content_type}')."
        ctx["max_size_mb"] = settings.MAX_UPLOAD_SIZE_MB
        return templates.TemplateResponse("upload.html", ctx, status_code=400)

    # Read file into memory (for production, prefer streaming directly to S3)
    raw = await video_file.read()
    if len(raw) > max_bytes:
        ctx = _base_ctx(request)
        ctx["error"] = (
            f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit "
            f"({len(raw) / 1024 / 1024:.1f} MB uploaded)."
        )
        ctx["max_size_mb"] = settings.MAX_UPLOAD_SIZE_MB
        return templates.TemplateResponse("upload.html", ctx, status_code=413)

    # ── Upload to S3 ───────────────────────────────────────────────────────────
    s3_key = s3_service.build_s3_key(video_file.filename or "video.mp4")
    try:
        s3_service.upload_fileobj(io.BytesIO(raw), s3_key, content_type)
    except RuntimeError as exc:
        ctx = _base_ctx(request)
        ctx["error"] = f"Upload to S3 failed: {exc}"
        ctx["max_size_mb"] = settings.MAX_UPLOAD_SIZE_MB
        return templates.TemplateResponse("upload.html", ctx, status_code=502)

    # ── Generate a UUID for the new video ─────────────────────────────────────
    import uuid as _uuid
    video_id = str(_uuid.uuid4())

    # ── Schedule DB logging as a background task ───────────────────────────────
    background_tasks.add_task(
        _log_upload_to_db,
        video_id=video_id,
        title=title.strip(),
        description=description.strip(),
        s3_key=s3_key,
        original_filename=video_file.filename or "video.mp4",
        content_type=content_type,
        file_size_bytes=len(raw),
    )

    # Redirect immediately; the background task writes the DB row after response
    return RedirectResponse(url=f"/video/{video_id}?uploaded=1", status_code=303)


@app.get("/video/{video_id}", response_class=HTMLResponse)
async def video_detail(
    video_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    uploaded: str = "",
):
    # The background task may still be running — poll a couple of times
    import asyncio

    video: Video | None = None
    for _ in range(6):          # up to ~3 s wait
        result = await db.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video:
            break
        await asyncio.sleep(0.5)

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Increment view count
    video.view_count += 1
    await db.commit()

    # Generate a presigned URL — this is what the <video> tag will use
    try:
        video_url = s3_service.generate_presigned_url(video.s3_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    ctx = _base_ctx(request)
    ctx["video"] = video
    ctx["video_url"] = video_url
    ctx["presigned_expiry_minutes"] = settings.PRESIGNED_URL_EXPIRY // 60
    ctx["just_uploaded"] = uploaded == "1"
    return templates.TemplateResponse("video_player.html", ctx)


@app.post("/video/{video_id}/delete")
async def delete_video(
    video_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video: Video | None = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Remove from S3 first (best-effort)
    s3_service.delete_object(video.s3_key)

    await db.delete(video)
    await db.commit()

    return RedirectResponse(url="/?deleted=1", status_code=303)
