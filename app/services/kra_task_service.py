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
from typing import Dict, Iterator, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kra_tasks import KraAssignment, KraDefinition, KraOccurrence
from app.models.models import User

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


def _insert_ignoring_conflicts(db: AsyncSession, rows: List[dict]):
    dialect = db.get_bind().dialect.name
    statement = (sqlite_insert if dialect == "sqlite" else pg_insert)(KraOccurrence).values(rows)
    return statement.on_conflict_do_nothing()


async def ensure_occurrences(
    db: AsyncSession,
    tenant_id: UUID,
    assignee_id: Optional[UUID] = None,
    property_id: Optional[UUID] = None,
    *,
    up_to_date: date,
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
        inserted = await db.execute(_insert_ignoring_conflicts(db, rows[i:i + _INSERT_BATCH]))
        result.created += max(inserted.rowcount, 0)
    if result.capped_assignments:
        logger.warning("[KRA TASKS] %s assignment(s) hit the %s period limit; older periods follow on later calls",
                       result.capped_assignments, MAX_PERIODS_PER_CALL)
    return result
