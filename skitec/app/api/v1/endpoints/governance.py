"""
Governance Router - Placeholder

Approval workflows and governance endpoints.
Workflow instantiation, approval, and rejection.

Endpoints to implement:
- GET /governance/workflows - List workflow templates
- POST /governance/workflows - Create workflow template
- GET /governance/instances - List workflow instances
- POST /governance/instances - Create workflow instance
- PUT /governance/instances/{id}/approve - Approve request
- PUT /governance/instances/{id}/reject - Reject request
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/governance",
    tags=["Governance"],
)


# TODO: Implement governance endpoints
