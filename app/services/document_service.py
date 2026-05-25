"""
Document Management Service - app/services/document_service.py

Business logic for document management operations
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Document, DocumentReview, DocumentApproval, DocumentVersion,
    DocumentShare, DocumentSignature, DocumentActivityLog, DocumentTemplate,
    User, Department, Tenant
)
from app.schemas.document_schemas import (
    DocumentUploadRequest, DocumentReviewRequest, DocumentApprovalRequest,
    DocumentShareRequest, DocumentSignatureRequest, DocumentSignatureSubmitRequest,
    DocumentSignatureDeclineRequest, DocumentTemplateRequest, DocumentSearchRequest
)


class DocumentService:
    """Service for document management operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ===========================================================
    # DOCUMENT OPERATIONS
    # ===========================================================

    async def create_document(
        self,
        tenant_id: UUID,
        property_id: Optional[UUID],
        file_name: str,
        file_path: str,
        file_size: int,
        file_type: str,
        uploaded_by: UUID,
        request: DocumentUploadRequest
    ) -> Document:
        """Create a new document"""
        file_extension = os.path.splitext(file_name)[1]
        
        document = Document(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            property_id=property_id,
            title=request.title,
            description=request.description,
            category=request.category,
            department=request.department,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            file_extension=file_extension,
            tags=request.tags,
            access_scope=request.access_scope.value,
            uploaded_by=uploaded_by,
            owner_id=uploaded_by,
            assigned_compliance_reviewer=request.assigned_compliance_reviewer,
            status="pending_review",
            approval_status="pending",
            is_confidential=request.is_confidential,
            retention_period=request.retention_period,
            expiry_date=request.expiry_date,
            requires_signature=request.requires_signature
        )
        
        self.db.add(document)
        await self.db.flush()
        
        # Create initial activity log
        await self._create_activity_log(
            document_id=document.id,
            tenant_id=tenant_id,
            action="uploaded",
            activity_type="document",
            performed_by=uploaded_by,
            description=f"Document '{request.title}' uploaded"
        )
        
        return document

    async def get_document(
        self,
        document_id: UUID,
        tenant_id: UUID
    ) -> Optional[Document]:
        """Get document by ID"""
        query = (
            select(Document)
            .where(
                and_(
                    Document.id == document_id,
                    Document.tenant_id == tenant_id,
                    Document.deleted_at == None
                )
            )
            .options(
                selectinload(Document.reviews),
                selectinload(Document.approvals),
                selectinload(Document.versions),
                selectinload(Document.shares),
                selectinload(Document.activity_logs),
                selectinload(Document.signatures)
            )
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_documents(
        self,
        tenant_id: UUID,
        property_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 20
    ) -> tuple[List[Document], int]:
        """List documents with pagination"""
        query = select(Document).where(
            and_(
                Document.tenant_id == tenant_id,
                Document.deleted_at == None
            )
        )
        
        if property_id:
            query = query.where(Document.property_id == property_id)
        
        # Get total count
        count_query = select(func.count()).select_from(Document).where(
            and_(
                Document.tenant_id == tenant_id,
                Document.deleted_at == None
            )
        )
        if property_id:
            count_query = count_query.where(Document.property_id == property_id)
        
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()
        
        # Get paginated results
        query = query.order_by(desc(Document.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        documents = result.scalars().all()
        
        return documents, total

    async def search_documents(
        self,
        tenant_id: UUID,
        search_request: DocumentSearchRequest
    ) -> tuple[List[Document], int]:
        """Search documents based on filters"""
        filters = [
            Document.tenant_id == tenant_id,
            Document.deleted_at == None
        ]
        
        if search_request.query:
            query_pattern = f"%{search_request.query}%"
            filters.append(
                or_(
                    Document.title.ilike(query_pattern),
                    Document.description.ilike(query_pattern),
                    Document.tags.ilike(query_pattern)
                )
            )
        
        if search_request.category:
            filters.append(Document.category == search_request.category)
        
        if search_request.status:
            filters.append(Document.status == search_request.status.value)
        
        if search_request.department:
            filters.append(Document.department == search_request.department)
        
        if search_request.uploaded_by:
            filters.append(Document.uploaded_by == search_request.uploaded_by)
        
        if search_request.date_from:
            filters.append(Document.created_at >= search_request.date_from)
        
        if search_request.date_to:
            filters.append(Document.created_at <= search_request.date_to)
        
        query = select(Document).where(and_(*filters))
        
        # Get total count
        count_result = await self.db.execute(
            select(func.count()).select_from(Document).where(and_(*filters))
        )
        total = count_result.scalar()
        
        # Get paginated results
        query = (
            query
            .order_by(desc(Document.created_at))
            .offset(search_request.skip)
            .limit(search_request.limit)
        )
        
        result = await self.db.execute(query)
        documents = result.scalars().all()
        
        return documents, total

    async def update_document_status(
        self,
        document_id: UUID,
        tenant_id: UUID,
        new_status: str,
        performed_by: UUID,
        details: Optional[str] = None
    ) -> Optional[Document]:
        """Update document status"""
        document = await self.get_document(document_id, tenant_id)
        if not document:
            return None
        
        old_status = document.status
        document.status = new_status
        document.last_modified = datetime.utcnow()
        
        await self.db.flush()
        
        # Create activity log
        await self._create_activity_log(
            document_id=document_id,
            tenant_id=tenant_id,
            action="status_changed",
            activity_type="document",
            performed_by=performed_by,
            description=f"Status changed from {old_status} to {new_status}",
            details={"old_status": old_status, "new_status": new_status}
        )
        
        return document

    async def delete_document(
        self,
        document_id: UUID,
        tenant_id: UUID,
        deleted_by: UUID
    ) -> bool:
        """Soft delete a document"""
        document = await self.get_document(document_id, tenant_id)
        if not document:
            return False
        
        document.deleted_at = datetime.utcnow()
        document.deleted_by = deleted_by
        
        await self.db.flush()
        
        # Create activity log
        await self._create_activity_log(
            document_id=document_id,
            tenant_id=tenant_id,
            action="deleted",
            activity_type="document",
            performed_by=deleted_by,
            description="Document deleted"
        )
        
        return True

    # ===========================================================
    # DOCUMENT REVIEW
    # ===========================================================

    async def assign_reviewer(
        self,
        document_id: UUID,
        tenant_id: UUID,
        reviewer_id: UUID,
        review_priority: str = "medium"
    ) -> Optional[DocumentReview]:
        """Assign a reviewer to a document"""
        review = DocumentReview(
            id=uuid.uuid4(),
            document_id=document_id,
            tenant_id=tenant_id,
            reviewer_id=reviewer_id,
            review_status="pending",
            review_priority=review_priority
        )
        
        self.db.add(review)
        await self.db.flush()
        
        # Update document to indicate review is assigned
        document = await self.get_document(document_id, tenant_id)
        if document:
            document.status = "pending_review"
            await self.db.flush()
            
            await self._create_activity_log(
                document_id=document_id,
                tenant_id=tenant_id,
                action="review_assigned",
                activity_type="review",
                performed_by=reviewer_id,
                description=f"Document assigned for review to {reviewer_id}"
            )
        
        return review

    async def submit_review(
        self,
        document_id: UUID,
        tenant_id: UUID,
        reviewer_id: UUID,
        request: DocumentReviewRequest
    ) -> Optional[DocumentReview]:
        """Submit a review for a document"""
        query = select(DocumentReview).where(
            and_(
                DocumentReview.document_id == document_id,
                DocumentReview.reviewer_id == reviewer_id,
                DocumentReview.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(query)
        review = result.scalars().first()
        
        if not review:
            return None
        
        review.review_status = request.review_status.value
        review.comments = request.comments
        review.rejection_reason = request.rejection_reason
        review.review_started_at = datetime.utcnow()
        review.completed_at = datetime.utcnow()
        review.requires_additional_info = request.requires_additional_info
        review.additional_info_request = request.additional_info_request
        
        await self.db.flush()
        
        # Create activity log
        await self._create_activity_log(
            document_id=document_id,
            tenant_id=tenant_id,
            action="review_submitted",
            activity_type="review",
            performed_by=reviewer_id,
            description=f"Review submitted: {request.review_status.value}"
        )
        
        return review

    # ===========================================================
    # DOCUMENT APPROVAL
    # ===========================================================

    async def assign_approver(
        self,
        document_id: UUID,
        tenant_id: UUID,
        approver_id: UUID,
        approver_role: Optional[str] = None
    ) -> Optional[DocumentApproval]:
        """Assign an approver to a document"""
        approval = DocumentApproval(
            id=uuid.uuid4(),
            document_id=document_id,
            tenant_id=tenant_id,
            approver_id=approver_id,
            approver_role=approver_role,
            approval_status="pending"
        )
        
        self.db.add(approval)
        await self.db.flush()
        
        # Update document approval status
        document = await self.get_document(document_id, tenant_id)
        if document:
            document.approval_status = "awaiting_approval"
            await self.db.flush()
            
            await self._create_activity_log(
                document_id=document_id,
                tenant_id=tenant_id,
                action="approver_assigned",
                activity_type="approval",
                performed_by=approver_id,
                description=f"Document assigned for approval"
            )
        
        return approval

    async def approve_document(
        self,
        document_id: UUID,
        tenant_id: UUID,
        approver_id: UUID,
        request: DocumentApprovalRequest
    ) -> Optional[DocumentApproval]:
        """Approve or reject a document"""
        query = select(DocumentApproval).where(
            and_(
                DocumentApproval.document_id == document_id,
                DocumentApproval.approver_id == approver_id,
                DocumentApproval.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(query)
        approval = result.scalars().first()
        
        if not approval:
            return None
        
        approval.approval_status = request.approval_status.value
        approval.approval_reason = request.approval_reason
        approval.conditions = request.conditions
        approval.decided_at = datetime.utcnow()
        
        await self.db.flush()
        
        # Update document status based on approval
        document = await self.get_document(document_id, tenant_id)
        if document:
            if request.approval_status.value == "approved":
                document.status = "approved"
                document.approval_status = "approved"
            elif request.approval_status.value == "rejected":
                document.status = "rejected"
                document.approval_status = "rejected"
            elif request.approval_status.value == "conditional_approval":
                document.approval_status = "conditional_approval"
            
            await self.db.flush()
            
            await self._create_activity_log(
                document_id=document_id,
                tenant_id=tenant_id,
                action="document_approved" if request.approval_status.value == "approved" else "document_rejected",
                activity_type="approval",
                performed_by=approver_id,
                description=f"Document {request.approval_status.value}: {request.approval_reason}"
            )
        
        return approval

    # ===========================================================
    # DOCUMENT SHARING
    # ===========================================================

    async def share_document(
        self,
        document_id: UUID,
        tenant_id: UUID,
        shared_by: UUID,
        request: DocumentShareRequest
    ) -> Optional[DocumentShare]:
        """Share a document with user or department"""
        # Check if already shared
        query = select(DocumentShare).where(
            and_(
                DocumentShare.document_id == document_id,
                DocumentShare.tenant_id == tenant_id,
                DocumentShare.shared_with_user_id == request.shared_with_user_id,
                DocumentShare.shared_with_department_id == request.shared_with_department_id
            )
        )
        result = await self.db.execute(query)
        existing_share = result.scalars().first()
        
        if existing_share:
            # Update existing share
            existing_share.permission_level = request.permission_level.value
            existing_share.expires_at = request.expires_at
            existing_share.is_active = True
            share = existing_share
        else:
            # Create new share
            share = DocumentShare(
                id=uuid.uuid4(),
                document_id=document_id,
                tenant_id=tenant_id,
                shared_with_user_id=request.shared_with_user_id,
                shared_with_department_id=request.shared_with_department_id,
                shared_by=shared_by,
                permission_level=request.permission_level.value,
                expires_at=request.expires_at
            )
            self.db.add(share)
        
        await self.db.flush()
        
        # Create activity log
        recipient = request.shared_with_user_id or request.shared_with_department_id
        await self._create_activity_log(
            document_id=document_id,
            tenant_id=tenant_id,
            action="document_shared",
            activity_type="share",
            performed_by=shared_by,
            description=f"Document shared with {recipient}"
        )
        
        return share

    async def revoke_document_share(
        self,
        share_id: UUID,
        tenant_id: UUID,
        revoked_by: UUID
    ) -> bool:
        """Revoke document share"""
        query = select(DocumentShare).where(
            and_(
                DocumentShare.id == share_id,
                DocumentShare.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(query)
        share = result.scalars().first()
        
        if not share:
            return False
        
        share.is_active = False
        await self.db.flush()
        
        # Create activity log
        await self._create_activity_log(
            document_id=share.document_id,
            tenant_id=tenant_id,
            action="share_revoked",
            activity_type="share",
            performed_by=revoked_by,
            description="Document share revoked"
        )
        
        return True

    # ===========================================================
    # DOCUMENT SIGNATURES
    # ===========================================================

    async def request_signature(
        self,
        document_id: UUID,
        tenant_id: UUID,
        requested_by: UUID,
        request: DocumentSignatureRequest
    ) -> Optional[DocumentSignature]:
        """Request signature for a document"""
        signature = DocumentSignature(
            id=uuid.uuid4(),
            document_id=document_id,
            tenant_id=tenant_id,
            signer_id=request.signer_id,
            signer_name=request.signer_name,
            signer_email=request.signer_email,
            signer_role=request.signer_role,
            signature_status="pending",
            signature_request_sent_at=datetime.utcnow()
        )
        
        self.db.add(signature)
        await self.db.flush()
        
        # Create activity log
        await self._create_activity_log(
            document_id=document_id,
            tenant_id=tenant_id,
            action="signature_requested",
            activity_type="signature",
            performed_by=requested_by,
            description=f"Signature requested from {request.signer_name}"
        )
        
        return signature

    async def submit_signature(
        self,
        signature_id: UUID,
        tenant_id: UUID,
        request: DocumentSignatureSubmitRequest
    ) -> Optional[DocumentSignature]:
        """Submit a signature"""
        query = select(DocumentSignature).where(
            and_(
                DocumentSignature.id == signature_id,
                DocumentSignature.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(query)
        signature = result.scalars().first()
        
        if not signature:
            return None
        
        signature.signature_image = request.signature_image
        signature.signature_status = "signed"
        signature.signed_at = datetime.utcnow()
        
        await self.db.flush()
        
        # Create activity log
        await self._create_activity_log(
            document_id=signature.document_id,
            tenant_id=tenant_id,
            action="signature_submitted",
            activity_type="signature",
            performed_by=signature.signer_id,
            description=f"Signature submitted by {signature.signer_name}"
        )
        
        return signature

    async def decline_signature(
        self,
        signature_id: UUID,
        tenant_id: UUID,
        request: DocumentSignatureDeclineRequest
    ) -> Optional[DocumentSignature]:
        """Decline to sign a document"""
        query = select(DocumentSignature).where(
            and_(
                DocumentSignature.id == signature_id,
                DocumentSignature.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(query)
        signature = result.scalars().first()
        
        if not signature:
            return None
        
        signature.signature_status = "rejected"
        signature.decline_reason = request.decline_reason
        
        await self.db.flush()
        
        # Create activity log
        await self._create_activity_log(
            document_id=signature.document_id,
            tenant_id=tenant_id,
            action="signature_declined",
            activity_type="signature",
            performed_by=signature.signer_id,
            description=f"Signature declined by {signature.signer_name}: {request.decline_reason}"
        )
        
        return signature

    # ===========================================================
    # DOCUMENT TEMPLATES
    # ===========================================================

    async def create_template(
        self,
        tenant_id: UUID,
        request: DocumentTemplateRequest
    ) -> DocumentTemplate:
        """Create a new document template"""
        template = DocumentTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=request.name,
            description=request.description,
            category=request.category,
            template_content=request.template_content,
            required_fields=request.required_fields,
            is_active=True
        )
        
        self.db.add(template)
        await self.db.flush()
        
        return template

    async def get_template(
        self,
        template_id: UUID,
        tenant_id: UUID
    ) -> Optional[DocumentTemplate]:
        """Get a document template"""
        query = select(DocumentTemplate).where(
            and_(
                DocumentTemplate.id == template_id,
                DocumentTemplate.tenant_id == tenant_id,
                DocumentTemplate.deleted_at == None
            )
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_templates(
        self,
        tenant_id: UUID,
        category: Optional[str] = None
    ) -> List[DocumentTemplate]:
        """List document templates"""
        query = select(DocumentTemplate).where(
            and_(
                DocumentTemplate.tenant_id == tenant_id,
                DocumentTemplate.is_active == True,
                DocumentTemplate.deleted_at == None
            )
        )
        
        if category:
            query = query.where(DocumentTemplate.category == category)
        
        result = await self.db.execute(query.order_by(DocumentTemplate.name))
        return result.scalars().all()

    # ===========================================================
    # STATISTICS & DASHBOARD
    # ===========================================================

    async def get_document_stats(
        self,
        tenant_id: UUID,
        property_id: Optional[UUID] = None
    ) -> dict:
        """Get document statistics for dashboard"""
        filters = [
            Document.tenant_id == tenant_id,
            Document.deleted_at == None
        ]
        
        if property_id:
            filters.append(Document.property_id == property_id)
        
        # Total files
        total_files_query = select(func.count()).select_from(Document).where(and_(*filters))
        total_files = (await self.db.execute(total_files_query)).scalar()
        
        # Pending reviews
        pending_reviews_query = select(func.count()).select_from(Document).where(
            and_(
                and_(*filters),
                Document.status == "pending_review"
            )
        )
        pending_reviews = (await self.db.execute(pending_reviews_query)).scalar()
        
        # Approved docs
        approved_docs_query = select(func.count()).select_from(Document).where(
            and_(
                and_(*filters),
                Document.status == "approved"
            )
        )
        approved_docs = (await self.db.execute(approved_docs_query)).scalar()
        
        # Rejected docs
        rejected_docs_query = select(func.count()).select_from(Document).where(
            and_(
                and_(*filters),
                Document.status == "rejected"
            )
        )
        rejected_docs = (await self.db.execute(rejected_docs_query)).scalar()
        
        # Recent uploads
        recent_uploads_query = select(func.count()).select_from(Document).where(
            and_(
                and_(*filters),
                Document.created_at >= datetime.utcnow() - timedelta(days=7)
            )
        )
        recent_uploads = (await self.db.execute(recent_uploads_query)).scalar()
        
        # Shared files
        shared_files_query = select(func.count(Document.id)).select_from(Document).join(
            DocumentShare, Document.id == DocumentShare.document_id
        ).where(
            and_(
                and_(*filters),
                DocumentShare.is_active == True
            )
        )
        shared_files = (await self.db.execute(shared_files_query)).scalar()
        
        # Total size
        total_size_query = select(func.sum(Document.file_size)).select_from(Document).where(and_(*filters))
        total_size_bytes = (await self.db.execute(total_size_query)).scalar() or 0
        total_size_gb = total_size_bytes / (1024 ** 3)
        
        return {
            "total_files": total_files or 0,
            "pending_reviews": pending_reviews or 0,
            "approved_docs": approved_docs or 0,
            "rejected_docs": rejected_docs or 0,
            "recent_uploads": recent_uploads or 0,
            "shared_files": shared_files or 0,
            "total_size_gb": round(total_size_gb, 2)
        }

    # ===========================================================
    # ACTIVITY LOGGING
    # ===========================================================

    async def _create_activity_log(
        self,
        document_id: UUID,
        tenant_id: UUID,
        action: str,
        activity_type: str,
        performed_by: UUID,
        description: str,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> DocumentActivityLog:
        """Create activity log entry"""
        log = DocumentActivityLog(
            id=uuid.uuid4(),
            document_id=document_id,
            tenant_id=tenant_id,
            action=action,
            activity_type=activity_type,
            performed_by=performed_by,
            description=description,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(log)
        await self.db.flush()
        
        return log
