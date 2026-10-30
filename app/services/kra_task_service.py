"""
Assigned KRA tasks - app/services/kra_task_service.py

Periods are calendar based: daily = the day, weekly = Monday..Sunday, monthly =
the calendar month, quarterly = the calendar quarter.

Occurrences are created on demand, because this hosting has no scheduler:
ensure_occurrences() fills in every period from an assignment's start_date up
to the period containing up_to_date, so a task nobody opened still exists and
counts as never completed. It is safe to call repeatedly and concurrently.
"""
import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kra_tasks import FREQUENCIES, KraAssignment, KraDefinition, KraOccurrence
from app.models.models import Role, User
from app.schemas.kra_tasks import DefinitionCreate, DefinitionUpdate, OccurrenceComplete, OccurrenceDelay
from app.services.geofence_scope import (
    PropertyNotInScope, assigned_property, caller_tenant, current_role, property_in_scope,
)

logger = logging.getLogger("skitech")

# Most periods created per assignment in one call: over a year of daily tasks.
# The newest missing periods are created first, and later calls continue with
# the older ones, so nothing recent is ever dropped and a backlog still fills in.
MAX_PERIODS_PER_CALL = 400
_INSERT_BATCH = 500


def period_for(frequency: str, day: date) -> Tuple[date, date]:
    """(period_start, period_end) of the period containing day."""
    if frequency == "daily":
        return day, day
    if frequency == "weekly":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if frequency == "monthly":
        return day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1])
    if frequency == "quarterly":
        first_month = 3 * ((day.month - 1) // 3) + 1
        last_month = first_month + 2
        return (date(day.year, first_month, 1),
                date(day.year, last_month, calendar.monthrange(day.year, last_month)[1]))
    raise ValueError(f"Unknown frequency: {frequency}")


def periods_newest_first(frequency: str, start_date: date, up_to_date: date) -> Iterator[Tuple[date, date]]:
    """Every period from the one containing up_to_date back to the one containing start_date."""
    if start_date > up_to_date:
        return
    first_start, _ = period_for(frequency, start_date)
    current = period_for(frequency, up_to_date)
    while current[0] >= first_start:
        yield current
        current = period_for(frequency, current[0] - timedelta(days=1))


def validate_client_today(today: date) -> date:
    """Properties have no timezone, so "today" is the client's local date. It
    may differ from the UTC date by at most one day (ValueError otherwise)."""
    if abs((today - datetime.utcnow().date()).days) > 1:
        raise ValueError("today must be within one day of the current UTC date")
    return today


@dataclass
class EnsureResult:
    created: int = 0
    capped_assignments: int = 0   # assignments with older periods left for a later call


def _insert_ignoring_conflicts(db: AsyncSession, model, rows: List[dict]):
    dialect = db.get_bind().dialect.name
    statement = (sqlite_insert if dialect == "sqlite" else pg_insert)(model).values(rows)
    return statement.on_conflict_do_nothing()


async def ensure_occurrences(
    db: AsyncSession,
    tenant_id: UUID,
    assignee_id: Optional[UUID] = None,
    property_id: Optional[UUID] = None,
    *,
    up_to_date: date,
    definition_id: Optional[UUID] = None,
    only_assignment_id: Optional[UUID] = None,
) -> EnsureResult:
    """Create the missing occurrences up to the period containing up_to_date.

    Skips ended assignments, deactivated or deleted definitions, and assignees
    who were deactivated or deleted. Existing rows are never changed. The
    caller commits.
    """
    conditions = [
        KraAssignment.tenant_id == tenant_id,
        KraAssignment.is_active == True,
        KraDefinition.is_active == True,
        KraDefinition.deleted_at == None,
        User.is_active == True,
        User.deleted_at == None,
    ]
    if assignee_id is not None:
        conditions.append(KraAssignment.assignee_id == assignee_id)
    if property_id is not None:
        conditions.append(KraAssignment.property_id == property_id)
    if definition_id is not None:
        conditions.append(KraAssignment.definition_id == definition_id)
    if only_assignment_id is not None:
        conditions.append(KraAssignment.id == only_assignment_id)

    assignments = (await db.execute(
        select(KraAssignment, KraDefinition.frequency)
        .join(KraDefinition, KraDefinition.id == KraAssignment.definition_id)
        .join(User, User.id == KraAssignment.assignee_id)
        .where(*conditions)
    )).all()
    if not assignments:
        return EnsureResult()

    existing: Dict[UUID, Set[date]] = {}
    found = await db.execute(
        select(KraOccurrence.assignment_id, KraOccurrence.period_start)
        .where(KraOccurrence.assignment_id.in_([a.id for a, _ in assignments]))
    )
    for assignment_id, period_start in found.all():
        existing.setdefault(assignment_id, set()).add(period_start)

    result = EnsureResult()
    rows: List[dict] = []
    for assignment, frequency in assignments:
        done = existing.get(assignment.id, set())
        queued = 0
        for start, end in periods_newest_first(frequency, assignment.start_date, up_to_date):
            if start in done:
                continue
            if queued == MAX_PERIODS_PER_CALL:
                result.capped_assignments += 1
                break
            rows.append({
                "id": uuid4(),
                "tenant_id": assignment.tenant_id,
                "property_id": assignment.property_id,
                "assignment_id": assignment.id,
                "definition_id": assignment.definition_id,
                "assignee_id": assignment.assignee_id,
                "period_start": start,
                "period_end": end,
            })
            queued += 1

    for i in range(0, len(rows), _INSERT_BATCH):
        inserted = await db.execute(_insert_ignoring_conflicts(db, KraOccurrence, rows[i:i + _INSERT_BATCH]))
        result.created += max(inserted.rowcount, 0)
    if result.capped_assignments:
        logger.warning("[KRA TASKS] %s assignment(s) hit the %s period limit; older periods follow on later calls",
                       result.capped_assignments, MAX_PERIODS_PER_CALL)
    return result


# ── Access rules ────────────────────────────────────────────────────────────

class TaskNotFound(LookupError):
    """Missing, other-tenant or out-of-scope id."""


class TaskForbidden(Exception):
    pass


class TaskConflict(Exception):
    pass


def _utc_today() -> date:
    return datetime.utcnow().date()


def _tenant(user: dict) -> UUID:
    tenant_id = caller_tenant(user)
    if tenant_id is None:
        raise TaskNotFound()
    return tenant_id


def _caller_id(user: dict) -> UUID:
    return UUID(str(user["user_id"]))


async def require_manager_now(db: AsyncSession, user: dict) -> None:
    """The JWT role can be up to one access-token lifetime old, so managing also
    needs the same role stored now: demoted or deactivated accounts get 403."""
    if await current_role(db, user) != user.get("role"):
        raise TaskForbidden("Your role has changed. Please sign in again.")


async def _in_scope(db: AsyncSession, property_id, user: dict) -> UUID:
    try:
        return await property_in_scope(db, property_id, user)
    except PropertyNotInScope:
        raise TaskNotFound()


async def _scope_filter(db: AsyncSession, user: dict, property_id: Optional[UUID]) -> Optional[UUID]:
    """The one property to limit a read to, or None for the caller's whole tenant."""
    if property_id is not None:
        return await _in_scope(db, property_id, user)
    limited_to = assigned_property(user)
    if limited_to is None and user.get("role") == "Manager":
        raise TaskForbidden("No property is assigned to your account")
    return limited_to


async def _definition_in_scope(db: AsyncSession, user: dict, definition_id: UUID) -> KraDefinition:
    definition = (await db.execute(select(KraDefinition).where(
        KraDefinition.id == definition_id,
        KraDefinition.tenant_id == _tenant(user),
        KraDefinition.deleted_at == None,
    ))).scalar_one_or_none()
    if definition is None:
        raise TaskNotFound()
    await _in_scope(db, definition.property_id, user)
    return definition


# ── Definitions ─────────────────────────────────────────────────────────────

async def create_definition(db: AsyncSession, user: dict, data: DefinitionCreate) -> KraDefinition:
    await require_manager_now(db, user)
    property_id = await _in_scope(db, data.property_id, user)
    definition = KraDefinition(
        tenant_id=_tenant(user), property_id=property_id, title=data.title, description=data.description,
        frequency=data.frequency, value_label=data.value_label, created_by=_caller_id(user),
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return definition


async def list_definitions(db: AsyncSession, user: dict, property_id: Optional[UUID]) -> Sequence[KraDefinition]:
    await require_manager_now(db, user)
    scope = await _scope_filter(db, user, property_id)
    query = select(KraDefinition).where(KraDefinition.tenant_id == _tenant(user), KraDefinition.deleted_at == None)
    if scope is not None:
        query = query.where(KraDefinition.property_id == scope)
    return (await db.execute(query.order_by(KraDefinition.created_at.desc(), KraDefinition.id))).scalars().all()


async def update_definition(db: AsyncSession, user: dict, definition_id: UUID, data: DefinitionUpdate) -> KraDefinition:
    await require_manager_now(db, user)
    definition = await _definition_in_scope(db, user, definition_id)
    changes = data.model_dump(exclude_unset=True)

    if "frequency" in changes and changes["frequency"] != definition.frequency:
        used = (await db.execute(select(KraAssignment.id).where(
            KraAssignment.definition_id == definition.id).limit(1))).first()
        if used:
            raise TaskConflict("Frequency cannot change once the task has been assigned")

    active = changes.get("is_active")
    if active is False and definition.is_active:
        # No generation after this, so periods up to now must exist first.
        await ensure_occurrences(db, definition.tenant_id, definition_id=definition.id, up_to_date=_utc_today())
    elif active is True and not definition.is_active:
        # The inactive gap is not missed work: restart generation from today.
        assignments = (await db.execute(select(KraAssignment).where(
            KraAssignment.definition_id == definition.id, KraAssignment.is_active == True))).scalars().all()
        for assignment in assignments:
            assignment.start_date = _utc_today()

    for field, value in changes.items():
        setattr(definition, field, value)
    await db.commit()
    await db.refresh(definition)
    return definition


# ── Assignments ─────────────────────────────────────────────────────────────

def _check_assignable(user: dict, definition: KraDefinition, target_role: str, target_property: Optional[UUID]) -> None:
    same_property = target_property == definition.property_id
    if target_role == "Staff":
        if not same_property:
            raise TaskNotFound()
    elif target_role == "Manager":
        if user.get("role") == "Manager":
            if not same_property:
                raise TaskNotFound()
            raise TaskForbidden("Managers can only assign staff")
        if not same_property and target_property is not None:
            raise TaskNotFound()
    else:
        raise TaskForbidden("KRA tasks can only be assigned to staff and managers")


async def assign_users(db: AsyncSession, user: dict, definition_id: UUID, user_ids: List[UUID], today: date):
    """Returns (new assignments, ids skipped because already actively assigned).
    Any user who can't be assigned fails the whole request; nothing is saved."""
    validate_client_today(today)
    await require_manager_now(db, user)
    definition = await _definition_in_scope(db, user, definition_id)
    if not definition.is_active:
        raise TaskConflict("This task is inactive")

    wanted = list(dict.fromkeys(user_ids))
    targets = (await db.execute(
        select(User.id, Role.name, User.property_id).join(Role, Role.id == User.role_id).where(
            User.id.in_(wanted), User.tenant_id == definition.tenant_id,
            User.is_active == True, User.deleted_at == None,
        )
    )).all()
    if len(targets) != len(wanted):
        raise TaskNotFound()
    for _, target_role, target_property in targets:
        _check_assignable(user, definition, target_role, target_property)

    already = set((await db.execute(select(KraAssignment.assignee_id).where(
        KraAssignment.definition_id == definition.id, KraAssignment.is_active == True,
        KraAssignment.assignee_id.in_(wanted),
    ))).scalars().all())
    rows = [{
        "id": uuid4(), "tenant_id": definition.tenant_id, "property_id": definition.property_id,
        "definition_id": definition.id, "assignee_id": target, "assigned_by": _caller_id(user),
        "start_date": today, "is_active": True,
    } for target in wanted if target not in already]
    if rows:
        # uq_kra_assignment_active settles two managers assigning at once.
        await db.execute(_insert_ignoring_conflicts(db, KraAssignment, rows))
    await db.commit()

    created = (await db.execute(select(KraAssignment).where(
        KraAssignment.id.in_([row["id"] for row in rows])))).scalars().all() if rows else []
    created_for = {a.assignee_id for a in created}
    return created, [target for target in wanted if target not in created_for]


async def end_assignment(db: AsyncSession, user: dict, assignment_id: UUID) -> KraAssignment:
    await require_manager_now(db, user)
    assignment = (await db.execute(select(KraAssignment).where(
        KraAssignment.id == assignment_id, KraAssignment.tenant_id == _tenant(user),
    ))).scalar_one_or_none()
    if assignment is None:
        raise TaskNotFound()
    await _in_scope(db, assignment.property_id, user)
    if not assignment.is_active:
        raise TaskConflict("This assignment has already ended")

    # No generation after this, so periods up to now must exist first.
    await ensure_occurrences(db, assignment.tenant_id, only_assignment_id=assignment.id, up_to_date=_utc_today())
    assignment.is_active = False
    assignment.ended_at = datetime.utcnow()
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def list_assignments(db: AsyncSession, user: dict, definition_id: Optional[UUID]) -> Sequence[KraAssignment]:
    await require_manager_now(db, user)
    query = select(KraAssignment).where(KraAssignment.tenant_id == _tenant(user))
    if definition_id is not None:
        definition = await _definition_in_scope(db, user, definition_id)
        query = query.where(KraAssignment.definition_id == definition.id)
    else:
        scope = await _scope_filter(db, user, None)
        if scope is not None:
            query = query.where(KraAssignment.property_id == scope)
    return (await db.execute(query.order_by(KraAssignment.start_date.desc(), KraAssignment.id))).scalars().all()


async def names_for(db: AsyncSession, user_ids) -> Dict[UUID, Optional[str]]:
    ids = list({i for i in user_ids if i is not None})
    if not ids:
        return {}
    rows = (await db.execute(select(User.id, User.first_name, User.last_name).where(User.id.in_(ids)))).all()
    return {r.id: f"{r.first_name or ''} {r.last_name or ''}".strip() or None for r in rows}


# ── Doing the work ──────────────────────────────────────────────────────────

def _occurrence_query():
    return select(
        KraOccurrence, KraDefinition.title, KraDefinition.description,
        KraDefinition.frequency, KraDefinition.value_label,
    ).join(KraDefinition, KraDefinition.id == KraOccurrence.definition_id)


async def my_occurrences(db: AsyncSession, user: dict, today: date):
    validate_client_today(today)
    tenant_id = _tenant(user)
    me = _caller_id(user)
    await ensure_occurrences(db, tenant_id, assignee_id=me, up_to_date=today)
    await db.commit()
    return (await db.execute(_occurrence_query().where(
        KraOccurrence.tenant_id == tenant_id,
        KraOccurrence.assignee_id == me,
        KraOccurrence.period_start <= today,
        or_(KraOccurrence.status != "completed", KraOccurrence.period_end >= today),
    ).order_by(KraOccurrence.period_start.desc(), KraDefinition.title, KraOccurrence.id))).all()


async def _own_occurrence(db: AsyncSession, user: dict, occurrence_id: UUID) -> KraOccurrence:
    occurrence = (await db.execute(select(KraOccurrence).where(
        KraOccurrence.id == occurrence_id, KraOccurrence.tenant_id == _tenant(user),
    ).with_for_update())).scalar_one_or_none()
    if occurrence is None:
        raise TaskNotFound()
    if occurrence.assignee_id != _caller_id(user):
        await _in_scope(db, occurrence.property_id, user)
        raise TaskForbidden("Only the person this task is assigned to can update it")
    return occurrence


async def _with_definition(db: AsyncSession, occurrence_id: UUID):
    return (await db.execute(_occurrence_query().where(KraOccurrence.id == occurrence_id))).one()


async def delay_occurrence(db: AsyncSession, user: dict, occurrence_id: UUID, data: OccurrenceDelay):
    occurrence = await _own_occurrence(db, user, occurrence_id)
    if occurrence.status != "pending":
        raise TaskConflict(f"This task is already {occurrence.status}")
    occurrence.status = "delayed"
    occurrence.was_delayed = True
    occurrence.delayed_at = datetime.utcnow()
    occurrence.delay_reason = data.reason
    await db.commit()
    await db.refresh(occurrence)
    return await _with_definition(db, occurrence.id)


async def complete_occurrence(db: AsyncSession, user: dict, occurrence_id: UUID, data: OccurrenceComplete):
    occurrence = await _own_occurrence(db, user, occurrence_id)
    if occurrence.status == "completed":
        raise TaskConflict("This task is already completed")
    value_label = (await db.execute(select(KraDefinition.value_label).where(
        KraDefinition.id == occurrence.definition_id))).scalar_one()
    if data.value is not None and value_label is None:
        raise ValueError("This task does not take a value")
    occurrence.status = "completed"
    occurrence.completed_at = datetime.utcnow()
    occurrence.completion_note = data.note
    occurrence.completion_value = data.value
    await db.commit()
    await db.refresh(occurrence)
    return await _with_definition(db, occurrence.id)


# ── Monitoring ──────────────────────────────────────────────────────────────

def _generate_up_to(period_to: Optional[date]) -> date:
    """These routes have no client date. period_to may be the viewer's local
    today, up to a day ahead of UTC; nothing further ahead is generated."""
    tomorrow = _utc_today() + timedelta(days=1)
    return _utc_today() if period_to is None else min(period_to, tomorrow)


def _period_conditions(period_from: Optional[date], period_to: Optional[date]) -> list:
    if period_from and period_to and period_from > period_to:
        raise ValueError("period_from must not be after period_to")
    conditions = []
    if period_from:
        conditions.append(KraOccurrence.period_end >= period_from)
    if period_to:
        conditions.append(KraOccurrence.period_start <= period_to)
    return conditions


async def _check_monitored_user(db: AsyncSession, user: dict, user_id: UUID, scope: Optional[UUID]) -> None:
    target = (await db.execute(select(User.id, User.property_id).where(
        User.id == user_id, User.tenant_id == _tenant(user), User.deleted_at == None,
    ))).first()
    if target is None or (scope is not None and target.property_id != scope):
        raise TaskNotFound()


async def list_occurrences(
    db: AsyncSession, user: dict, property_id: Optional[UUID], user_id: Optional[UUID], frequency: Optional[str],
    status: Optional[str], period_from: Optional[date], period_to: Optional[date], skip: int, limit: int,
):
    await require_manager_now(db, user)
    conditions = _period_conditions(period_from, period_to)
    scope = await _scope_filter(db, user, property_id)
    if user_id is not None:
        await _check_monitored_user(db, user, user_id, scope)
    tenant_id = _tenant(user)
    await ensure_occurrences(db, tenant_id, assignee_id=user_id, property_id=scope,
                             up_to_date=_generate_up_to(period_to))
    await db.commit()

    conditions.append(KraOccurrence.tenant_id == tenant_id)
    if scope is not None:
        conditions.append(KraOccurrence.property_id == scope)
    if user_id is not None:
        conditions.append(KraOccurrence.assignee_id == user_id)
    if frequency:
        conditions.append(KraDefinition.frequency == frequency)
    if status == "completed_delayed":
        conditions += [KraOccurrence.status == "completed", KraOccurrence.was_delayed == True]
    elif status:
        conditions.append(KraOccurrence.status == status)

    total = (await db.execute(
        select(func.count()).select_from(KraOccurrence)
        .join(KraDefinition, KraDefinition.id == KraOccurrence.definition_id).where(*conditions)
    )).scalar_one()
    rows = (await db.execute(_occurrence_query().where(*conditions).order_by(
        KraOccurrence.period_start.desc(), KraOccurrence.id).offset(skip).limit(limit))).all()
    return rows, total


async def summarize(db: AsyncSession, user: dict, property_id: Optional[UUID],
                    period_from: Optional[date], period_to: Optional[date]) -> dict:
    await require_manager_now(db, user)
    conditions = _period_conditions(period_from, period_to)
    scope = await _scope_filter(db, user, property_id)
    tenant_id = _tenant(user)
    await ensure_occurrences(db, tenant_id, property_id=scope, up_to_date=_generate_up_to(period_to))
    await db.commit()

    conditions.append(KraOccurrence.tenant_id == tenant_id)
    if scope is not None:
        conditions.append(KraOccurrence.property_id == scope)
    rows = (await db.execute(
        select(KraDefinition.frequency, KraOccurrence.status, KraOccurrence.was_delayed, func.count())
        .join(KraDefinition, KraDefinition.id == KraOccurrence.definition_id).where(*conditions)
        .group_by(KraDefinition.frequency, KraOccurrence.status, KraOccurrence.was_delayed)
    )).all()

    def blank():
        return {"pending": 0, "delayed": 0, "completed": 0, "completed_with_delay": 0, "total": 0}

    by_frequency = {name: {"frequency": name, **blank()} for name in FREQUENCIES}
    totals = blank()
    for frequency, status, was_delayed, count in rows:
        for bucket in (by_frequency[frequency], totals):
            bucket[status] += count
            bucket["total"] += count
            if status == "completed" and was_delayed:
                bucket["completed_with_delay"] += count
    return {"property_id": scope, "period_from": period_from, "period_to": period_to,
            "by_frequency": list(by_frequency.values()), "totals": totals}
