"""
Properties Routes - app/api/v1/endpoints/properties.py

Full CRUD for Properties + nested OwnerDetails.
Tenant isolation enforced via JWT tenant_id.
"""

import asyncio
import logging
import shutil
import uuid as uuid_lib
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.models import OwnerDetails, Property
from app.schemas.schemas import (
    OwnerDetailsCreate, OwnerDetailsResponse, OwnerDetailsUpdate,
    PropertyCreate, PropertyResponse, PropertyUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/properties", tags=["Properties"])


# ── Helpers ──────────────────────────────────────────────

async def _get_property_or_404(db: AsyncSession, property_id: UUID, tenant_id: UUID) -> Property:
    result = await db.execute(
        select(Property).where(
            Property.id == property_id,
            Property.tenant_id == tenant_id,
            Property.deleted_at == None,
        )
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


# ── Property CRUD ─────────────────────────────────────────

@router.post("/", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(
    data: PropertyCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    tenant_id = UUID(user["tenant_id"])

    # Check duplicate name within tenant
    dup = await db.execute(
        select(Property).where(
            Property.tenant_id == tenant_id,
            Property.name == data.name,
            Property.deleted_at == None,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A property with this name already exists")

    prop = Property(
        tenant_id=tenant_id,
        **data.model_dump(),
    )
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    return prop


@router.get("/", response_model=List[PropertyResponse])
async def list_properties(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_property")),
):
    tenant_id = UUID(user["tenant_id"])
    result = await db.execute(
        select(Property)
        .where(Property.tenant_id == tenant_id, Property.deleted_at == None)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_property")),
):
    return await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))


@router.put("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: UUID,
    data: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    prop = await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(prop, k, v)
    await db.commit()
    await db.refresh(prop)
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_200_OK)
async def delete_property(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    prop = await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))
    prop.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Property deleted successfully"}


# ── Owner Details ─────────────────────────────────────────

@router.post("/{property_id}/owner", response_model=OwnerDetailsResponse, status_code=201)
async def create_owner(
    property_id: UUID,
    data: OwnerDetailsCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_owner")),
):
    tenant_id = UUID(user["tenant_id"])
    await _get_property_or_404(db, property_id, tenant_id)

    owner = OwnerDetails(tenant_id=tenant_id, property_id=property_id, **data.model_dump())
    db.add(owner)
    await db.commit()
    await db.refresh(owner)
    return owner


@router.get("/{property_id}/owner", response_model=List[OwnerDetailsResponse])
async def list_owners(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_owner")),
):
    tenant_id = UUID(user["tenant_id"])
    await _get_property_or_404(db, property_id, tenant_id)
    result = await db.execute(
        select(OwnerDetails).where(
            OwnerDetails.property_id == property_id,
            OwnerDetails.tenant_id == tenant_id,
        )
    )
    return result.scalars().all()


@router.put("/{property_id}/owner/{owner_id}", response_model=OwnerDetailsResponse)
async def update_owner(
    property_id: UUID,
    owner_id: UUID,
    data: OwnerDetailsUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_owner")),
):
    result = await db.execute(
        select(OwnerDetails).where(
            OwnerDetails.id == owner_id,
            OwnerDetails.property_id == property_id,
            OwnerDetails.tenant_id == UUID(user["tenant_id"]),
        )
    )
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(owner, k, v)
    await db.commit()
    await db.refresh(owner)
    return owner


# ── Property Image Upload ──────────────────────────────────

@router.get("/{property_id}/images/upload-url")
async def get_property_image_upload_url(
    property_id: UUID,
    filename: str = Query(...),
    file_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    """Generate a pre-signed S3 PUT URL for uploading a property image."""
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise HTTPException(status_code=503, detail="S3 upload is not configured on this server")

    await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))

    tenant_id = user["tenant_id"]
    object_key = f"{tenant_id}/properties/{property_id}/{filename}"

    try:
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        presigned_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.S3_PROPERTY_IMAGES_BUCKET, "Key": object_key, "ContentType": file_type},
            ExpiresIn=3600,
        )
        public_url = f"https://{settings.S3_PROPERTY_IMAGES_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{object_key}"
        return {"upload_url": presigned_url, "file_key": object_key, "public_url": public_url}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
LOCAL_UPLOAD_DIR = Path("uploads/property_images")

# Module-level S3 client — created once when credentials are present.
_s3_client = None


def _get_s3_client():
    """Return a cached boto3 S3 client, creating it on first call."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _s3_client


@router.post("/{property_id}/images/upload")
async def upload_property_image(
    property_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_property")),
):
    """Upload a property image. Uses S3 when configured, otherwise saves locally."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, and WEBP images are allowed")

    await _get_property_or_404(db, property_id, UUID(user["tenant_id"]))
    tenant_id = user["tenant_id"]

    # Read file bytes once (async, non-blocking)
    contents = await file.read()
    ext = (file.filename or "image.jpg").rsplit(".", 1)[-1].lower() or "jpg"
    content_type = file.content_type or "image/jpeg"

    # ── S3 path (used when AWS credentials are configured) ──
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        object_key = f"{tenant_id}/properties/{property_id}/{uuid_lib.uuid4().hex}.{ext}"
        try:
            s3 = _get_s3_client()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: s3.put_object(
                    Bucket=settings.S3_PROPERTY_IMAGES_BUCKET,
                    Key=object_key,
                    Body=contents,
                    ContentType=content_type,
                ),
            )
            url = (
                f"https://{settings.S3_PROPERTY_IMAGES_BUCKET}"
                f".s3.{settings.AWS_REGION}.amazonaws.com/{object_key}"
            )
            logger.info("Property image uploaded to S3: %s", object_key)
            return {"url": url, "storage": "s3"}
        except ClientError as exc:
            logger.error("S3 upload failed for property %s: %s", property_id, exc)
            raise HTTPException(
                status_code=502,
                detail=f"Image storage unavailable: {exc.response['Error']['Message']}",
            )
        except Exception as exc:
            logger.error("Unexpected S3 error for property %s: %s", property_id, exc)
            raise HTTPException(status_code=500, detail="Failed to upload image to S3")

    # ── Local fallback (development / no S3 credentials) ───
    logger.warning(
        "No AWS credentials configured — saving property image locally (ephemeral on Render)"
    )
    save_dir = LOCAL_UPLOAD_DIR / tenant_id / str(property_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid_lib.uuid4().hex}.{ext}"
    save_path = save_dir / filename
    with save_path.open("wb") as out:
        out.write(contents)

    url = f"{settings.BACKEND_URL}/uploads/property_images/{tenant_id}/{property_id}/{filename}"
    return {"url": url, "storage": "local"}
