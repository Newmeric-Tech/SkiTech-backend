"""
KRA Service

Handles KRA business logic and database operations.
Implements tenant-level filtering and validation.
"""

from datetime import date
from typing import Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kra import DailyKRA, WeeklyKRA, MonthlyKRA, QuarterlyKRA
from app.models.workforce_entry import WorkforceEntry
from app.schemas.kra import (
    DailyKRACreate,
    DailyKRAUpdate,
    WeeklyKRACreate,
    WeeklyKRAUpdate,
    MonthlyKRACreate,
    MonthlyKRAUpdate,
    QuarterlyKRACreate,
    QuarterlyKRAUpdate,
)


class DailyKRAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_daily_kra(self, tenant_id: int, user_id: int, kra_data: DailyKRACreate) -> DailyKRA:
        db_kra = DailyKRA(
            tenant_id=tenant_id,
            user_id=user_id,
            date=kra_data.date,
            shift_changeover_status=kra_data.shift_changeover_status,
            guest_checkin_count=kra_data.guest_checkin_count,
            guest_checkout_count=kra_data.guest_checkout_count,
            complaints_logged=kra_data.complaints_logged,
            room_availability_checked=kra_data.room_availability_checked,
            maintenance_tasks=kra_data.maintenance_tasks,
            cash_deposit_amount=kra_data.cash_deposit_amount,
            google_reviews_count=kra_data.google_reviews_count,
            notes=kra_data.notes,
            is_submitted=True,
        )
        self.db.add(db_kra)
        await self.db.flush()
        return db_kra

    async def get_daily_kra_by_id(self, kra_id: int, tenant_id: int) -> Optional[DailyKRA]:
        result = await self.db.execute(
            select(DailyKRA).where(
                and_(DailyKRA.id == kra_id, DailyKRA.tenant_id == tenant_id, DailyKRA.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    async def get_daily_kra_by_date(self, tenant_id: int, user_id: int, kra_date: date) -> Optional[DailyKRA]:
        result = await self.db.execute(
            select(DailyKRA).where(
                and_(
                    DailyKRA.tenant_id == tenant_id,
                    DailyKRA.user_id == user_id,
                    DailyKRA.date == kra_date,
                    DailyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_daily_kras(
        self, tenant_id: int, user_id: Optional[int] = None, skip: int = 0, limit: int = 20
    ) -> Tuple[list, int]:
        query = select(DailyKRA).where(and_(DailyKRA.tenant_id == tenant_id, DailyKRA.deleted_at.is_(None)))
        count_query = select(func.count()).select_from(DailyKRA).where(
            and_(DailyKRA.tenant_id == tenant_id, DailyKRA.deleted_at.is_(None))
        )
        if user_id:
            query = query.where(DailyKRA.user_id == user_id)
            count_query = count_query.where(DailyKRA.user_id == user_id)

        total = (await self.db.execute(count_query)).scalar_one()
        result = await self.db.execute(query.order_by(desc(DailyKRA.date)).offset(skip).limit(limit))
        return result.scalars().all(), total

    async def calculate_compliance(
        self,
        tenant_id: int,
        start_date: date,
        end_date: date,
        employee_id: Optional[int] = None,
        property_id: Optional[int] = None,
    ) -> dict:
        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")

        total_days = (end_date - start_date).days + 1

        if employee_id is not None:
            employee_ids = [employee_id]
        elif property_id is not None:
            workforce_result = await self.db.execute(
                select(WorkforceEntry.id).where(
                    and_(WorkforceEntry.property_id == property_id, WorkforceEntry.deleted_at.is_(None))
                )
            )
            employee_ids = [row[0] for row in workforce_result.all()]
        else:
            users_result = await self.db.execute(
                select(DailyKRA.user_id)
                .where(
                    and_(
                        DailyKRA.tenant_id == tenant_id,
                        DailyKRA.date >= start_date,
                        DailyKRA.date <= end_date,
                        DailyKRA.deleted_at.is_(None),
                    )
                )
                .distinct()
            )
            employee_ids = [row[0] for row in users_result.all()]

        if not employee_ids:
            return {
                "tenant_id": tenant_id, "employee_id": employee_id, "property_id": property_id,
                "start_date": start_date, "end_date": end_date, "total_days": total_days,
                "expected_submissions": 0, "actual_submissions": 0, "compliance_percentage": 0.0,
            }

        expected_submissions = total_days * len(employee_ids)
        submissions_result = await self.db.execute(
            select(DailyKRA.user_id, DailyKRA.date).where(
                and_(
                    DailyKRA.tenant_id == tenant_id,
                    DailyKRA.user_id.in_(employee_ids),
                    DailyKRA.date >= start_date,
                    DailyKRA.date <= end_date,
                    DailyKRA.is_submitted.is_(True),
                    DailyKRA.deleted_at.is_(None),
                )
            )
        )
        actual_submissions = len({(row.user_id, row.date) for row in submissions_result.all()})
        compliance_percentage = round((actual_submissions / expected_submissions) * 100, 2)

        return {
            "tenant_id": tenant_id, "employee_id": employee_id, "property_id": property_id,
            "start_date": start_date, "end_date": end_date, "total_days": total_days,
            "expected_submissions": expected_submissions, "actual_submissions": actual_submissions,
            "compliance_percentage": compliance_percentage,
        }

    async def update_daily_kra(self, kra: DailyKRA, update_data: DailyKRAUpdate) -> DailyKRA:
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(kra, field, value)
        await self.db.flush()
        return kra

    async def delete_daily_kra(self, kra: DailyKRA) -> None:
        kra.soft_delete()
        await self.db.flush()


class WeeklyKRAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_weekly_kra(self, tenant_id: int, user_id: int, kra_data: WeeklyKRACreate) -> WeeklyKRA:
        db_kra = WeeklyKRA(
            tenant_id=tenant_id, user_id=user_id,
            week_starting_date=kra_data.week_starting_date, year=kra_data.year,
            week_number=kra_data.week_number, ota_images_uploaded=kra_data.ota_images_uploaded,
            ota_platforms=kra_data.ota_platforms, supply_stock_reviewed=kra_data.supply_stock_reviewed,
            supply_notes=kra_data.supply_notes, notes=kra_data.notes, is_submitted=True,
        )
        self.db.add(db_kra)
        await self.db.flush()
        return db_kra

    async def get_weekly_kra_by_id(self, kra_id: int, tenant_id: int) -> Optional[WeeklyKRA]:
        result = await self.db.execute(
            select(WeeklyKRA).where(
                and_(WeeklyKRA.id == kra_id, WeeklyKRA.tenant_id == tenant_id, WeeklyKRA.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    async def get_weekly_kra_by_week(
        self, tenant_id: int, user_id: int, year: int, week_number: int
    ) -> Optional[WeeklyKRA]:
        result = await self.db.execute(
            select(WeeklyKRA).where(
                and_(
                    WeeklyKRA.tenant_id == tenant_id, WeeklyKRA.user_id == user_id,
                    WeeklyKRA.year == year, WeeklyKRA.week_number == week_number,
                    WeeklyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_weekly_kras(
        self, tenant_id: int, user_id: Optional[int] = None, skip: int = 0, limit: int = 20
    ) -> Tuple[list, int]:
        query = select(WeeklyKRA).where(and_(WeeklyKRA.tenant_id == tenant_id, WeeklyKRA.deleted_at.is_(None)))
        count_query = select(func.count()).select_from(WeeklyKRA).where(
            and_(WeeklyKRA.tenant_id == tenant_id, WeeklyKRA.deleted_at.is_(None))
        )
        if user_id:
            query = query.where(WeeklyKRA.user_id == user_id)
            count_query = count_query.where(WeeklyKRA.user_id == user_id)
        total = (await self.db.execute(count_query)).scalar_one()
        result = await self.db.execute(
            query.order_by(desc(WeeklyKRA.week_starting_date)).offset(skip).limit(limit)
        )
        return result.scalars().all(), total

    async def update_weekly_kra(self, kra: WeeklyKRA, update_data: WeeklyKRAUpdate) -> WeeklyKRA:
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(kra, field, value)
        await self.db.flush()
        return kra

    async def delete_weekly_kra(self, kra: WeeklyKRA) -> None:
        kra.soft_delete()
        await self.db.flush()


class MonthlyKRAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_monthly_kra(self, tenant_id: int, user_id: int, kra_data: MonthlyKRACreate) -> MonthlyKRA:
        db_kra = MonthlyKRA(
            tenant_id=tenant_id, user_id=user_id, month=kra_data.month, year=kra_data.year,
            revenue_report_url=kra_data.revenue_report_url, notes=kra_data.notes, is_submitted=True,
        )
        self.db.add(db_kra)
        await self.db.flush()
        return db_kra

    async def get_monthly_kra_by_id(self, kra_id: int, tenant_id: int) -> Optional[MonthlyKRA]:
        result = await self.db.execute(
            select(MonthlyKRA).where(
                and_(MonthlyKRA.id == kra_id, MonthlyKRA.tenant_id == tenant_id, MonthlyKRA.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    async def get_monthly_kra_by_month(
        self, tenant_id: int, user_id: int, month: int, year: int
    ) -> Optional[MonthlyKRA]:
        result = await self.db.execute(
            select(MonthlyKRA).where(
                and_(
                    MonthlyKRA.tenant_id == tenant_id, MonthlyKRA.user_id == user_id,
                    MonthlyKRA.month == month, MonthlyKRA.year == year, MonthlyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_monthly_kras(
        self, tenant_id: int, user_id: Optional[int] = None, skip: int = 0, limit: int = 20
    ) -> Tuple[list, int]:
        query = select(MonthlyKRA).where(and_(MonthlyKRA.tenant_id == tenant_id, MonthlyKRA.deleted_at.is_(None)))
        count_query = select(func.count()).select_from(MonthlyKRA).where(
            and_(MonthlyKRA.tenant_id == tenant_id, MonthlyKRA.deleted_at.is_(None))
        )
        if user_id:
            query = query.where(MonthlyKRA.user_id == user_id)
            count_query = count_query.where(MonthlyKRA.user_id == user_id)
        total = (await self.db.execute(count_query)).scalar_one()
        result = await self.db.execute(
            query.order_by(desc(MonthlyKRA.year), desc(MonthlyKRA.month)).offset(skip).limit(limit)
        )
        return result.scalars().all(), total

    async def update_monthly_kra(self, kra: MonthlyKRA, update_data: MonthlyKRAUpdate) -> MonthlyKRA:
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(kra, field, value)
        await self.db.flush()
        return kra

    async def delete_monthly_kra(self, kra: MonthlyKRA) -> None:
        kra.soft_delete()
        await self.db.flush()


class QuarterlyKRAService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_quarterly_kra(self, tenant_id: int, user_id: int, kra_data: QuarterlyKRACreate) -> QuarterlyKRA:
        db_kra = QuarterlyKRA(
            tenant_id=tenant_id, user_id=user_id, quarter=kra_data.quarter, year=kra_data.year,
            revenue_report_url=kra_data.revenue_report_url, notes=kra_data.notes, is_submitted=True,
        )
        self.db.add(db_kra)
        await self.db.flush()
        return db_kra

    async def get_quarterly_kra_by_id(self, kra_id: int, tenant_id: int) -> Optional[QuarterlyKRA]:
        result = await self.db.execute(
            select(QuarterlyKRA).where(
                and_(QuarterlyKRA.id == kra_id, QuarterlyKRA.tenant_id == tenant_id, QuarterlyKRA.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    async def get_quarterly_kra_by_quarter(
        self, tenant_id: int, user_id: int, quarter: int, year: int
    ) -> Optional[QuarterlyKRA]:
        result = await self.db.execute(
            select(QuarterlyKRA).where(
                and_(
                    QuarterlyKRA.tenant_id == tenant_id, QuarterlyKRA.user_id == user_id,
                    QuarterlyKRA.quarter == quarter, QuarterlyKRA.year == year, QuarterlyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_quarterly_kras(
        self, tenant_id: int, user_id: Optional[int] = None, skip: int = 0, limit: int = 20
    ) -> Tuple[list, int]:
        query = select(QuarterlyKRA).where(
            and_(QuarterlyKRA.tenant_id == tenant_id, QuarterlyKRA.deleted_at.is_(None))
        )
        count_query = select(func.count()).select_from(QuarterlyKRA).where(
            and_(QuarterlyKRA.tenant_id == tenant_id, QuarterlyKRA.deleted_at.is_(None))
        )
        if user_id:
            query = query.where(QuarterlyKRA.user_id == user_id)
            count_query = count_query.where(QuarterlyKRA.user_id == user_id)
        total = (await self.db.execute(count_query)).scalar_one()
        result = await self.db.execute(
            query.order_by(desc(QuarterlyKRA.year), desc(QuarterlyKRA.quarter)).offset(skip).limit(limit)
        )
        return result.scalars().all(), total

    async def update_quarterly_kra(self, kra: QuarterlyKRA, update_data: QuarterlyKRAUpdate) -> QuarterlyKRA:
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(kra, field, value)
        await self.db.flush()
        return kra

    async def delete_quarterly_kra(self, kra: QuarterlyKRA) -> None:
        kra.soft_delete()
        await self.db.flush()
