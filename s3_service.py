"""
s3_service.py
All Boto3 / S3 interactions for StreamVault.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import PurePosixPath
from typing import BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import settings

logger = logging.getLogger(__name__)


def _make_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


def build_s3_key(original_filename: str) -> str:
    """Generate a unique, safe S3 object key from the original filename."""
    suffix = PurePosixPath(original_filename).suffix.lower()
    return f"videos/{uuid.uuid4()}{suffix}"


def upload_fileobj(fileobj: BinaryIO, s3_key: str, content_type: str) -> None:
    """
    Upload a file-like object to S3.
    Raises RuntimeError on failure so callers get a clean error message.
    """
    client = _make_client()
    try:
        client.upload_fileobj(
            fileobj,
            settings.S3_BUCKET_NAME,
            s3_key,
            ExtraArgs={
                "ContentType": content_type,
                # Private — access only via presigned URLs
                "ACL": "private",
            },
        )
        logger.info("Uploaded s3://%s/%s", settings.S3_BUCKET_NAME, s3_key)
    except (BotoCoreError, ClientError) as exc:
        logger.exception("S3 upload failed for key %s", s3_key)
        raise RuntimeError(f"S3 upload failed: {exc}") from exc


def generate_presigned_url(s3_key: str, expiry: int | None = None) -> str:
    """
    Return a presigned GET URL for the given S3 key.
    The URL is valid for `expiry` seconds (defaults to settings.PRESIGNED_URL_EXPIRY).
    """
    expiry = expiry or settings.PRESIGNED_URL_EXPIRY
    client = _make_client()
    try:
        url: str = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expiry,
        )
        return url
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Could not generate presigned URL for key %s", s3_key)
        raise RuntimeError(f"Presigned URL generation failed: {exc}") from exc


def delete_object(s3_key: str) -> None:
    """Delete an object from the bucket (best-effort; logs on failure)."""
    client = _make_client()
    try:
        client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
        logger.info("Deleted s3://%s/%s", settings.S3_BUCKET_NAME, s3_key)
    except (BotoCoreError, ClientError):
        logger.exception("Failed to delete S3 object %s", s3_key)


def guess_content_type(filename: str) -> str:
    """Return MIME type inferred from filename, defaulting to binary stream."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"
