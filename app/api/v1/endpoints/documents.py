"""
Document Management API Endpoints - app/api/v1/endpoints/documents.py

REST API routes for document management operations
"""

import os
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import (
    APIRouter, Depends, File, UploadFile, Form, HTTPException,
    status, Query
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, Document
from app.schemas.document_schemas import (
    DocumentUploadRequest, DocumentMetadataResponse, DocumentDetailResponse,
    DocumentReviewRequest, DocumentReviewResponse, AssignReviewerRequest,
    DocumentApprovalRequest, DocumentApprovalResponse, AssignApproverRequest,
    DocumentShareRequest, DocumentShareResponse, DocumentSignatureRequest,
    DocumentSignatureSubmitRequest, DocumentSignatureDeclineRequest,
    DocumentSignatureResponse, DocumentActivityLogResponse,
    DocumentTemplateRequest, DocumentTemplateResponse, DocumentOperationResponse,
    DocumentStats, DocumentSearchRequest, DocumentSearchResponse
)
from app.services.document_service import DocumentService


router = APIRouter(prefix="/documents", tags=["documents"])


# ===========================================================
# DOCUMENT UPLOAD & RETRIEVAL
# ===========================================================

@router.post("/upload", response_model=DocumentMetadataResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    category: str = Form(...),
    description: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    access_scope: str = Form("organization_wide"),
    assigned_compliance_reviewer: Optional[str] = Form(None),
    is_confidential: bool = Form(False),
    requires_signature: bool = Form(False),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentMetadataResponse:
    """
    Upload a new document
    
    - **title**: Document title
    - **category**: Document category (e.g., Operational Records, Financial)
    - **file**: Document file to upload
    """
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty"
        )
    
    # Generate file path (S3 or local storage)
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = f"documents/{current_user.tenant_id}/{unique_filename}"
    
    # TODO: Upload to S3 or local storage
    # For now, just store the path
    
    # Create document
    service = DocumentService(db)
    
    upload_request = DocumentUploadRequest(
        title=title,
        description=description,
        category=category,
        department=department,
        tags=tags,
        access_scope=access_scope,
        assigned_compliance_reviewer=uuid.UUID(assigned_compliance_reviewer) if assigned_compliance_reviewer else None,
        is_confidential=is_confidential,
        requires_signature=requires_signature
    )
    
    document = await service.create_document(
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id,
        file_name=file.filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file.content_type or "application/octet-stream",
        uploaded_by=current_user.id,
        request=upload_request
    )
    
    await db.commit()
    
    return DocumentMetadataResponse.from_attributes(document)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentDetailResponse:
    """Get document details with all related information"""
    
    try:
        doc_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    service = DocumentService(db)
    document = await service.get_document(doc_id, current_user.tenant_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return DocumentDetailResponse.from_attributes(document)


@router.get("", response_model=List[DocumentMetadataResponse])
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[DocumentMetadataResponse]:
    """List all documents"""
    
    service = DocumentService(db)
    documents, _ = await service.list_documents(
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id,
        skip=skip,
        limit=limit
    )
    
    return [DocumentMetadataResponse.from_attributes(doc) for doc in documents]


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentSearchResponse:
    """Search documents with filters"""
    
    service = DocumentService(db)
    documents, total = await service.search_documents(
        tenant_id=current_user.tenant_id,
        search_request=request
    )
    
    return DocumentSearchResponse(
        total=total,
        documents=[DocumentMetadataResponse.from_attributes(doc) for doc in documents],
        skip=request.skip,
        limit=request.limit
    )


# ===========================================================
# DOCUMENT REVIEW
# ===========================================================

@router.post("/{document_id}/assign-reviewer", response_model=DocumentReviewResponse)
async def assign_reviewer(
    document_id: str,
    request: AssignReviewerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentReviewResponse:
    """Assign a reviewer to the document"""
    
    try:
        doc_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    service = DocumentService(db)
    
    # Check if document exists
    document = await service.get_document(doc_id, current_user.tenant_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    review = await service.assign_reviewer(
        document_id=doc_id,
        tenant_id=current_user.tenant_id,
        reviewer_id=request.reviewer_id,
        review_priority=request.review_priority
    )
    
    await db.commit()
    
    return DocumentReviewResponse.from_attributes(review)


@router.post("/{document_id}/submit-review", response_model=DocumentReviewResponse)
async def submit_review(
    document_id: str,
    request: DocumentReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentReviewResponse:
    """Submit a review for the document"""
    
    try:
        doc_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    service = DocumentService(db)
    
    review = await service.submit_review(
        document_id=doc_id,
        tenant_id=current_user.tenant_id,
        reviewer_id=current_user.id,
        request=request
    )
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found or not assigned to you"
        )
    
    await db.commit()
    
    return DocumentReviewResponse.from_attributes(review)


# ===========================================================
# DOCUMENT APPROVAL
# ===========================================================

@router.post("/{document_id}/assign-approver", response_model=DocumentApprovalResponse)
async def assign_approver(
    document_id: str,
    request: AssignApproverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentApprovalResponse:
    """Assign an approver to the document"""
    
    try:
        doc_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    service = DocumentService(db)
    
    # Check if document exists
    document = await service.get_document(doc_id, current_user.tenant_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    approval = await service.assign_approver(
        document_id=doc_id,
        tenant_id=current_user.tenant_id,
        approver_id=request.approver_id,
        approver_role=request.approver_role
    )
    
    await db.commit()
    
    return DocumentApprovalResponse.from_attributes(approval)


@router.post("/{document_id}/approve", response_model=DocumentApprovalResponse)
async def approve_document(
    document_id: str,
    request: DocumentApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentApprovalResponse:
    """Approve or reject the document"""
    
    try:
        doc_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    service = DocumentService(db)
    
    approval = await service.approve_document(
        document_id=doc_id,
        tenant_id=current_user.tenant_id,
        approver_id=current_user.id,
        request=request
    )
    
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found or not assigned to you"
        )
    
    await db.commit()
    
    return DocumentApprovalResponse.from_attributes(approval)


# ===========================================================
# DOCUMENT SHARING
# ===========================================================

@router.post("/{document_id}/share", response_model=DocumentShareResponse)
async def share_document(
    document_id: str,
    request: DocumentShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentShareResponse:
    """Share a document with user or department"""
    
    try:
        doc_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    if not request.shared_with_user_id and not request.shared_with_department_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either shared_with_user_id or shared_with_department_id must be provided"
        )
    
    service = DocumentService(db)
    
    # Check if document exists
    document = await service.get_document(doc_id, current_user.tenant_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    share = await service.share_document(
        document_id=doc_id,
        tenant_id=current_user.tenant_id,
        shared_by=current_user.id,
        request=request
    )
    
    await db.commit()
    
    return DocumentShareResponse.from_attributes(share)


@router.delete("/share/{share_id}", response_model=DocumentOperationResponse)
async def revoke_share(
    share_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentOperationResponse:
    """Revoke document share"""
    
    try:
        s_id = uuid.UUID(share_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid share ID format"
        )
    
    service = DocumentService(db)
    success = await service.revoke_document_share(s_id, current_user.tenant_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share not found"
        )
    
    await db.commit()
    
    return DocumentOperationResponse(
        success=True,
        message="Share revoked successfully"
    )


# ===========================================================
# DOCUMENT SIGNATURES
# ===========================================================

@router.post("/{document_id}/request-signature", response_model=DocumentSignatureResponse)
async def request_signature(
    document_id: str,
    request: DocumentSignatureRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentSignatureResponse:
    """Request signature for document"""
    
    try:
        doc_id = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID format"
        )
    
    service = DocumentService(db)
    
    # Check if document exists
    document = await service.get_document(doc_id, current_user.tenant_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    signature = await service.request_signature(
        document_id=doc_id,
        tenant_id=current_user.tenant_id,
        requested_by=current_user.id,
        request=request
    )
    
    await db.commit()
    
    return DocumentSignatureResponse.from_attributes(signature)


@router.post("/signature/{signature_id}/submit", response_model=DocumentSignatureResponse)
async def submit_signature(
    signature_id: str,
    request: DocumentSignatureSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentSignatureResponse:
    """Submit signature"""
    
    try:
        sig_id = uuid.UUID(signature_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature ID format"
        )
    
    service = DocumentService(db)
    
    signature = await service.submit_signature(sig_id, current_user.tenant_id, request)
    
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature request not found"
        )
    
    await db.commit()
    
    return DocumentSignatureResponse.from_attributes(signature)


@router.post("/signature/{signature_id}/decline", response_model=DocumentSignatureResponse)
async def decline_signature(
    signature_id: str,
    request: DocumentSignatureDeclineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentSignatureResponse:
    """Decline to sign document"""
    
    try:
        sig_id = uuid.UUID(signature_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature ID format"
        )
    
    service = DocumentService(db)
    
    signature = await service.decline_signature(sig_id, current_user.tenant_id, request)
    
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature request not found"
        )
    
    await db.commit()
    
    return DocumentSignatureResponse.from_attributes(signature)


# ===========================================================
# DOCUMENT TEMPLATES
# ===========================================================

@router.post("/templates", response_model=DocumentTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: DocumentTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentTemplateResponse:
    """Create a document template"""
    
    service = DocumentService(db)
    template = await service.create_template(current_user.tenant_id, request)
    
    await db.commit()
    
    return DocumentTemplateResponse.from_attributes(template)


@router.get("/templates/{template_id}", response_model=DocumentTemplateResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentTemplateResponse:
    """Get document template"""
    
    try:
        t_id = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid template ID format"
        )
    
    service = DocumentService(db)
    template = await service.get_template(t_id, current_user.tenant_id)
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    return DocumentTemplateResponse.from_attributes(template)


@router.get("/templates", response_model=List[DocumentTemplateResponse])
async def list_templates(
    category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[DocumentTemplateResponse]:
    """List document templates"""
    
    service = DocumentService(db)
    templates = await service.list_templates(current_user.tenant_id, category)
    
    return [DocumentTemplateResponse.from_attributes(t) for t in templates]


# ===========================================================
# STATISTICS & DASHBOARD
# ===========================================================

@router.get("/stats", response_model=DocumentStats)
async def get_document_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> DocumentStats:
    """Get document statistics for dashboard"""
    
    service = DocumentService(db)
    stats = await service.get_document_stats(
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id
    )
    
    return DocumentStats(**stats)
