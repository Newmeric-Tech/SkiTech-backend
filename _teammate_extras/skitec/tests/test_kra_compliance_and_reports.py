"""Tests for KRA compliance, daily aggregation, and pagination totals."""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workforce import WorkforceEntry
from app.schemas.kra import DailyKRACreate
from app.services.kra_service import DailyKRAService


@pytest.mark.asyncio
async def test_calculate_compliance_for_employee(db_session: AsyncSession):
    """Compliance should reflect submitted days over expected days for an employee."""
    service = DailyKRAService(db_session)
    start_date = date.today() - timedelta(days=2)

    for offset in [0, 1]:
        kra_data = DailyKRACreate(
            date=start_date + timedelta(days=offset),
            shift_changeover_status=True,
            guest_checkin_count=5,
            guest_checkout_count=4,
            complaints_logged=1,
            room_availability_checked=True,
            maintenance_tasks=1,
            cash_deposit_amount=100.0,
            google_reviews_count=2,
            notes="submitted",
        )
        await service.create_daily_kra(tenant_id=1, user_id=10, kra_data=kra_data)

    await db_session.flush()

    result = await service.calculate_compliance(
        tenant_id=1,
        start_date=start_date,
        end_date=start_date + timedelta(days=2),
        employee_id=10,
    )

    assert result["expected_submissions"] == 3
    assert result["actual_submissions"] == 2
    assert result["compliance_percentage"] == 66.67


@pytest.mark.asyncio
async def test_aggregate_daily_data_with_property_filter(db_session: AsyncSession):
    """Daily report should aggregate only records mapped to a property."""
    service = DailyKRAService(db_session)
    report_day = date.today() - timedelta(days=1)

    workforce = WorkforceEntry(
        first_name="Alex",
        last_name="Taylor",
        email="alex.taylor@example.com",
        phone="1234567890",
        property_id=99,
        employee_id="EMP-99-1",
        position="Front Desk",
        department="Operations",
        is_active=True,
        start_date=report_day - timedelta(days=30),
        end_date=None,
        scheduled_hours_per_week=40,
        notes="",
    )
    db_session.add(workforce)
    await db_session.flush()

    matched_kra = DailyKRACreate(
        date=report_day,
        shift_changeover_status=True,
        guest_checkin_count=8,
        guest_checkout_count=6,
        complaints_logged=2,
        room_availability_checked=True,
        maintenance_tasks=3,
        cash_deposit_amount=450.0,
        google_reviews_count=4,
        notes="property matched",
    )
    await service.create_daily_kra(tenant_id=1, user_id=workforce.id, kra_data=matched_kra)

    unmatched_kra = DailyKRACreate(
        date=report_day,
        shift_changeover_status=True,
        guest_checkin_count=50,
        guest_checkout_count=40,
        complaints_logged=20,
        room_availability_checked=True,
        maintenance_tasks=10,
        cash_deposit_amount=5000.0,
        google_reviews_count=12,
        notes="property unmatched",
    )
    await service.create_daily_kra(tenant_id=1, user_id=999, kra_data=unmatched_kra)

    await db_session.flush()

    result = await service.aggregate_daily_data(
        tenant_id=1,
        start_date=report_day,
        end_date=report_day,
        property_id=99,
    )

    assert result["summary"]["records_count"] == 1
    assert result["summary"]["total_checkins"] == 8
    assert result["summary"]["total_checkouts"] == 6
    assert result["summary"]["total_complaints"] == 2
    assert result["summary"]["total_maintenance_tasks"] == 3
    assert result["summary"]["total_google_reviews"] == 4
    assert result["summary"]["total_cash_deposit"] == 450.0


@pytest.mark.asyncio
async def test_list_daily_kras_total_respects_user_filter(db_session: AsyncSession):
    """Paginated total should match the filtered dataset size."""
    service = DailyKRAService(db_session)
    base_day = date.today() - timedelta(days=3)

    for idx in range(3):
        user_id = 42 if idx < 2 else 43
        kra_data = DailyKRACreate(
            date=base_day + timedelta(days=idx),
            shift_changeover_status=True,
            guest_checkin_count=1,
            guest_checkout_count=1,
            complaints_logged=0,
            room_availability_checked=True,
            maintenance_tasks=0,
            cash_deposit_amount=10.0,
            google_reviews_count=0,
            notes="pagination",
        )
        await service.create_daily_kra(tenant_id=1, user_id=user_id, kra_data=kra_data)

    await db_session.flush()

    rows, total = await service.list_daily_kras(
        tenant_id=1,
        user_id=42,
        skip=0,
        limit=10,
    )

    assert len(rows) == 2
    assert total == 2
