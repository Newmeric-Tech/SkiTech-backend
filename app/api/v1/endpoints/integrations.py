from typing import List
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user_obj
from app.models.models import User

from app.schemas.channel_manager import (
    TestConnectionRequest,
    IntegrationCreate,
    IntegrationOut
)
from app.utils.crypto import encrypt
from app.services.adapters import get_adapter
from app.services.sync_service import sync_single_integration

router = APIRouter()


@router.get("/integrations", response_model=List[IntegrationOut])
async def get_integrations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    tenant_id = current_user.tenant_id

    query = text("""
        SELECT i.id, i.provider_name, i.property_id, p.name as property_name,
               i.connection_status, i.last_sync_at, i.error_message
        FROM integrations i
        JOIN properties p ON i.property_id = p.id
        WHERE i.tenant_id = :tenant_id AND i.connection_status != 'disconnected'
        ORDER BY i.created_at DESC
    """)
    result = (await db.execute(query, {"tenant_id": tenant_id})).fetchall()
    
    # Map raw SQL rows to schema
    integrations = []
    for row in result:
        integrations.append(
            IntegrationOut(
                id=row.id,
                provider_name=row.provider_name,
                property_id=row.property_id,
                property_name=row.property_name,
                connection_status=row.connection_status,
                last_sync_at=row.last_sync_at,
                error_message=row.error_message
            )
        )
    return integrations


@router.post("/integrations", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: IntegrationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    tenant_id = current_user.tenant_id

    # 1. Verify property belongs to user's tenant
    property_query = text("SELECT id, name FROM properties WHERE id = :id AND tenant_id = :tenant_id")
    property_check = (await db.execute(property_query, {"id": payload.property_id, "tenant_id": tenant_id})).fetchone()
    if not property_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Property not found or does not belong to this tenant."
        )

    # 2. Validate connection before saving
    try:
        adapter = get_adapter(payload.provider_name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    test_result = await adapter.test_connection(payload.credentials)
    if not test_result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection validation failed: {test_result['message']}"
        )

    # 3. Encrypt credentials
    credentials_json = json.dumps(payload.credentials)
    encrypted_credentials = encrypt(credentials_json)

    # 4. Save to database using UPSERT
    upsert_query = text("""
        INSERT INTO integrations (tenant_id, property_id, provider_name, credentials_json, connection_status, last_sync_at, error_message, updated_at)
        VALUES (:tenant_id, :property_id, :provider_name, :credentials_json, 'active', NULL, NULL, NOW())
        ON CONFLICT (property_id, provider_name)
        DO UPDATE SET
            credentials_json = EXCLUDED.credentials_json,
            connection_status = 'active',
            error_message = NULL,
            updated_at = NOW()
        RETURNING id, tenant_id, provider_name, property_id, credentials_json, connection_status, last_sync_at, error_message
    """)

    saved_integration = (await db.execute(upsert_query, {
        "tenant_id": tenant_id,
        "property_id": payload.property_id,
        "provider_name": payload.provider_name,
        "credentials_json": encrypted_credentials
    })).fetchone()
    await db.commit()

    # 5. Trigger manual background sync task asynchronously
    background_tasks.add_task(sync_single_integration, saved_integration)

    return IntegrationOut(
        id=saved_integration.id,
        provider_name=saved_integration.provider_name,
        property_id=saved_integration.property_id,
        property_name=property_check.name,
        connection_status=saved_integration.connection_status,
        last_sync_at=saved_integration.last_sync_at,
        error_message=saved_integration.error_message
    )


@router.post("/integrations/test")
async def test_integration_connection(
    payload: TestConnectionRequest,
    current_user: User = Depends(get_current_user_obj)
):
    try:
        adapter = get_adapter(payload.provider_name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    result = await adapter.test_connection(payload.credentials)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
    return {"success": True, "message": result["message"]}


@router.delete("/integrations/{integration_id}")
async def disconnect_integration(
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    tenant_id = current_user.tenant_id

    # Soft delete - set status to 'disconnected'
    query = text("""
        UPDATE integrations
        SET connection_status = 'disconnected', updated_at = NOW()
        WHERE id = :id AND tenant_id = :tenant_id
    """)
    res = await db.execute(query, {"id": integration_id, "tenant_id": tenant_id})
    await db.commit()

    if res.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found or does not belong to this tenant."
        )

    return {"success": True, "message": "Integration disconnected successfully."}


@router.post("/integrations/{integration_id}/sync")
async def trigger_manual_sync(
    integration_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_obj)
):
    tenant_id = current_user.tenant_id

    query = text("""
        SELECT * FROM integrations
        WHERE id = :id AND tenant_id = :tenant_id AND connection_status != 'disconnected'
    """)
    integration = (await db.execute(query, {"id": integration_id, "tenant_id": tenant_id})).fetchone()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found or is currently disconnected."
        )

    background_tasks.add_task(sync_single_integration, integration)
    return {"success": True, "message": "Manual sync triggered in the background."}
