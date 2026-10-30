"""
Assigned KRA task routes - app/api/v1/endpoints/kra_tasks.py

Managers (own property) and admins build tasks and assign them; the assignee
marks each period's task delayed or completed; managers and admins monitor.
Other-tenant and out-of-scope ids answer 404. See
app/services/kra_task_service.py for the rules. Separate from /kra/...
"""
import logging
from datetime import date
from functools import wraps
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.schemas.kra_tasks import (
    AssignRequest, AssignResponse, AssignmentResponse, DefinitionCreate, DefinitionResponse, DefinitionUpdate,
    DisplayStatus, Frequency, OccurrenceComplete, OccurrenceDelay, OccurrencePage, OccurrenceResponse,
    SummaryResponse,
)
from app.services import kra_task_service as tasks
from app.services.kra_task_service import TaskConflict, TaskForbidden, TaskNotFound
from app.utils.safe_errors import log_safe_exception

logger = logging.getLogger("skitech")

router = APIRouter(prefix="/kra-tasks", tags=["KRA Tasks"])

# Co Admin is allowed through require_roles wherever Tenant Admin is.
MANAGE = Depends(require_roles(["Super Admin", "Tenant Admin", "Manager"]))


def _route(fn):
    """Maps service errors to responses. ValueError messages are written by the
    service for the user; anything else is logged safely and stays generic."""
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except HTTPException:
            raise
        except TaskNotFound:
            await kwargs["db"].rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        except TaskForbidden as err:
            await kwargs["db"].rollback()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err))
        except TaskConflict as err:
            await kwargs["db"].rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
        except ValueError as err:
            await kwargs["db"].rollback()
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))
        except Exception as err:
            await kwargs["db"].rollback()
            log_safe_exception(logger, f"[KRA TASKS] {fn.__name__} failed", err)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="An unexpected error occurred.")
    return wrapper


def _display_status(status_value: str, was_delayed: bool) -> str:
    if status_value == "completed":
        return "completed_delayed" if was_delayed else "completed"
    return status_value


async def _occurrences(db: AsyncSession, rows) -> List[OccurrenceResponse]:
    names = await tasks.names_for(db, [row[0].assignee_id for row in rows])
    out = []
    for occurrence, title, description, frequency, value_label in rows:
        out.append(OccurrenceResponse(
            id=occurrence.id, tenant_id=occurrence.tenant_id, property_id=occurrence.property_id,
            assignment_id=occurrence.assignment_id, definition_id=occurrence.definition_id,
            assignee_id=occurrence.assignee_id, assignee_name=names.get(occurrence.assignee_id),
            title=title, description=description, frequency=frequency, value_label=value_label,
            period_start=occurrence.period_start, period_end=occurrence.period_end,
            status=occurrence.status, display_status=_display_status(occurrence.status, occurrence.was_delayed),
            was_delayed=occurrence.was_delayed, delayed_at=occurrence.delayed_at,
            delay_reason=occurrence.delay_reason, completed_at=occurrence.completed_at,
            completion_note=occurrence.completion_note, completion_value=occurrence.completion_value,
            created_at=occurrence.created_at, updated_at=occurrence.updated_at,
        ))
    return out


async def _assignments(db: AsyncSession, items) -> List[AssignmentResponse]:
    names = await tasks.names_for(db, [a.assignee_id for a in items])
    out = []
    for assignment in items:
        response = AssignmentResponse.model_validate(assignment)
        response.assignee_name = names.get(assignment.assignee_id)
        out.append(response)
    return out


# ── Definitions and assignments ─────────────────────────────────────────────

@router.post("/definitions", response_model=DefinitionResponse, status_code=status.HTTP_201_CREATED)
@_route
async def create_definition(data: DefinitionCreate, db: AsyncSession = Depends(get_db), user: dict = MANAGE):
    return await tasks.create_definition(db, user, data)


@router.get("/definitions", response_model=List[DefinitionResponse])
@_route
async def list_definitions(property_id: Optional[UUID] = None, db: AsyncSession = Depends(get_db), user: dict = MANAGE):
    return await tasks.list_definitions(db, user, property_id)


@router.put("/definitions/{definition_id}", response_model=DefinitionResponse)
@_route
async def update_definition(definition_id: UUID, data: DefinitionUpdate,
                            db: AsyncSession = Depends(get_db), user: dict = MANAGE):
    return await tasks.update_definition(db, user, definition_id, data)


@router.post("/definitions/{definition_id}/assignments", response_model=AssignResponse,
             status_code=status.HTTP_201_CREATED)
@_route
async def assign_definition(definition_id: UUID, data: AssignRequest,
                            db: AsyncSession = Depends(get_db), user: dict = MANAGE):
    created, skipped = await tasks.assign_users(db, user, definition_id, data.user_ids, data.today)
    return AssignResponse(created=await _assignments(db, created), skipped_user_ids=skipped)


@router.delete("/assignments/{assignment_id}", response_model=AssignmentResponse)
@_route
async def end_assignment(assignment_id: UUID, db: AsyncSession = Depends(get_db), user: dict = MANAGE):
    assignment = await tasks.end_assignment(db, user, assignment_id)
    return (await _assignments(db, [assignment]))[0]


@router.get("/assignments", response_model=List[AssignmentResponse])
@_route
async def list_assignments(definition_id: Optional[UUID] = None, db: AsyncSession = Depends(get_db),
                           user: dict = MANAGE):
    return await _assignments(db, await tasks.list_assignments(db, user, definition_id))


# ── Doing the work ──────────────────────────────────────────────────────────

@router.get("/my", response_model=List[OccurrenceResponse])
@_route
async def my_tasks(today: date, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    return await _occurrences(db, await tasks.my_occurrences(db, user, today))


@router.post("/occurrences/{occurrence_id}/delay", response_model=OccurrenceResponse)
@_route
async def delay_task(occurrence_id: UUID, data: OccurrenceDelay, db: AsyncSession = Depends(get_db),
                     user: dict = Depends(get_current_user)):
    return (await _occurrences(db, [await tasks.delay_occurrence(db, user, occurrence_id, data)]))[0]


@router.post("/occurrences/{occurrence_id}/complete", response_model=OccurrenceResponse)
@_route
async def complete_task(occurrence_id: UUID, data: OccurrenceComplete, db: AsyncSession = Depends(get_db),
                        user: dict = Depends(get_current_user)):
    return (await _occurrences(db, [await tasks.complete_occurrence(db, user, occurrence_id, data)]))[0]


# ── Monitoring ──────────────────────────────────────────────────────────────

@router.get("/occurrences", response_model=OccurrencePage)
@_route
async def list_occurrences(
    property_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    frequency: Optional[Frequency] = None,
    status_filter: Optional[DisplayStatus] = Query(None, alias="status"),
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = MANAGE,
):
    rows, total = await tasks.list_occurrences(db, user, property_id, user_id, frequency, status_filter,
                                               period_from, period_to, skip, limit)
    return OccurrencePage(items=await _occurrences(db, rows), total=total, skip=skip, limit=limit)


@router.get("/summary", response_model=SummaryResponse)
@_route
async def summary(property_id: Optional[UUID] = None, period_from: Optional[date] = None,
                  period_to: Optional[date] = None, db: AsyncSession = Depends(get_db), user: dict = MANAGE):
    return await tasks.summarize(db, user, property_id, period_from, period_to)
