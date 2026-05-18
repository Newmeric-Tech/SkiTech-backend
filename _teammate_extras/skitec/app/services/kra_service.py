"""
KRA Service

Handles KRA business logic and database operations.
Implements tenant-level filtering and validation.
"""

from datetime import date
from typing import Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.kra import DailyKRA, WeeklyKRA, MonthlyKRA, QuarterlyKRA
from ..models.workforce import WorkforceEntry
from ..schemas.kra import (
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
    """Service for daily KRA operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize daily KRA service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def create_daily_kra(
        self,
        tenant_id: int,
        user_id: int,
        kra_data: DailyKRACreate,
    ) -> DailyKRA:
        """
        Create new daily KRA

        Args:
            tenant_id: Tenant ID for multi-tenancy
            user_id: User ID creating the KRA
            kra_data: Daily KRA data

        Returns:
            Created DailyKRA object
        """
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

    async def get_daily_kra_by_id(
        self,
        kra_id: int,
        tenant_id: int,
    ) -> Optional[DailyKRA]:
        """
        Get daily KRA by ID with tenant filtering

        Args:
            kra_id: KRA ID to retrieve
            tenant_id: Tenant ID for filtering

        Returns:
            DailyKRA object if found and belongs to tenant, None otherwise
        """
        result = await self.db.execute(
            select(DailyKRA).where(
                and_(
                    DailyKRA.id == kra_id,
                    DailyKRA.tenant_id == tenant_id,
                    DailyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_daily_kra_by_date(
        self,
        tenant_id: int,
        user_id: int,
        kra_date: date,
    ) -> Optional[DailyKRA]:
        """
        Get daily KRA for specific date and user

        Args:
            tenant_id: Tenant ID for filtering
            user_id: User ID for filtering
            kra_date: Date to query

        Returns:
            DailyKRA object if found, None otherwise
        """
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
        self,
        tenant_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[list[DailyKRA], int]:
        """
        List daily KRAs with tenant filtering

        Args:
            tenant_id: Tenant ID for filtering
            user_id: Optional user ID to filter by specific user
            skip: Number of records to skip
            limit: Number of records to return

        Returns:
            Tuple of (list of DailyKRA objects, total count)
        """
        query = select(DailyKRA).where(
            and_(
                DailyKRA.tenant_id == tenant_id,
                DailyKRA.deleted_at.is_(None),
            )
        )

        if user_id:
            query = query.where(DailyKRA.user_id == user_id)

        count_query = select(func.count()).select_from(DailyKRA).where(
            and_(
                DailyKRA.tenant_id == tenant_id,
                DailyKRA.deleted_at.is_(None),
            )
        )
        if user_id:
            count_query = count_query.where(DailyKRA.user_id == user_id)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Get paginated results
        result = await self.db.execute(
            query.order_by(desc(DailyKRA.date))
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all(), total

    async def calculate_compliance(
        self,
        tenant_id: int,
        start_date: date,
        end_date: date,
        employee_id: Optional[int] = None,
        property_id: Optional[int] = None,
    ) -> dict:
        """
        Calculate KRA compliance percentage over a date range.

        Compliance is defined as:
            actual_submissions / expected_submissions * 100
        where expected submissions are the number of tracked users multiplied by
        the number of days in range.
        """
        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")

        total_days = (end_date - start_date).days + 1

        if employee_id is not None:
            employee_ids = [employee_id]
        elif property_id is not None:
            workforce_result = await self.db.execute(
                select(WorkforceEntry.id).where(
                    and_(
                        WorkforceEntry.property_id == property_id,
                        WorkforceEntry.deleted_at.is_(None),
                    )
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
                "tenant_id": tenant_id,
                "employee_id": employee_id,
                "property_id": property_id,
                "start_date": start_date,
                "end_date": end_date,
                "total_days": total_days,
                "expected_submissions": 0,
                "actual_submissions": 0,
                "compliance_percentage": 0.0,
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

        unique_submissions = {
            (row.user_id, row.date) for row in submissions_result.all()
        }
        actual_submissions = len(unique_submissions)
        compliance_percentage = round((actual_submissions / expected_submissions) * 100, 2)

        return {
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "property_id": property_id,
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
            "expected_submissions": expected_submissions,
            "actual_submissions": actual_submissions,
            "compliance_percentage": compliance_percentage,
        }

    async def aggregate_daily_data(
        self,
        tenant_id: int,
        start_date: date,
        end_date: date,
        employee_id: Optional[int] = None,
        property_id: Optional[int] = None,
    ) -> dict:
        """Aggregate daily KRA metrics for reporting."""
        if end_date < start_date:
            raise ValueError("end_date cannot be before start_date")

        filters = [
            DailyKRA.tenant_id == tenant_id,
            DailyKRA.date >= start_date,
            DailyKRA.date <= end_date,
            DailyKRA.deleted_at.is_(None),
        ]

        if employee_id is not None:
            filters.append(DailyKRA.user_id == employee_id)
        elif property_id is not None:
            workforce_result = await self.db.execute(
                select(WorkforceEntry.id).where(
                    and_(
                        WorkforceEntry.property_id == property_id,
                        WorkforceEntry.deleted_at.is_(None),
                    )
                )
            )
            employee_ids = [row[0] for row in workforce_result.all()]
            if not employee_ids:
                total_days = (end_date - start_date).days + 1
                return {
                    "tenant_id": tenant_id,
                    "employee_id": employee_id,
                    "property_id": property_id,
                    "summary": {
                        "start_date": start_date,
                        "end_date": end_date,
                        "total_days": total_days,
                        "records_count": 0,
                        "total_checkins": 0,
                        "total_checkouts": 0,
                        "total_complaints": 0,
                        "total_maintenance_tasks": 0,
                        "total_google_reviews": 0,
                        "total_cash_deposit": 0.0,
                    },
                    "daily": [],
                }
            filters.append(DailyKRA.user_id.in_(employee_ids))

        query = (
            select(
                DailyKRA.date.label("report_date"),
                func.count(DailyKRA.id).label("records_count"),
                func.coalesce(func.sum(DailyKRA.guest_checkin_count), 0).label("total_checkins"),
                func.coalesce(func.sum(DailyKRA.guest_checkout_count), 0).label("total_checkouts"),
                func.coalesce(func.sum(DailyKRA.complaints_logged), 0).label("total_complaints"),
                func.coalesce(func.sum(DailyKRA.maintenance_tasks), 0).label("total_maintenance_tasks"),
                func.coalesce(func.sum(DailyKRA.google_reviews_count), 0).label("total_google_reviews"),
                func.coalesce(func.sum(DailyKRA.cash_deposit_amount), 0.0).label("total_cash_deposit"),
            )
            .where(and_(*filters))
            .group_by(DailyKRA.date)
            .order_by(DailyKRA.date)
        )

        result = await self.db.execute(query)
        daily = []
        for row in result.all():
            daily.append(
                {
                    "report_date": row.report_date,
                    "records_count": int(row.records_count),
                    "total_checkins": int(row.total_checkins),
                    "total_checkouts": int(row.total_checkouts),
                    "total_complaints": int(row.total_complaints),
                    "total_maintenance_tasks": int(row.total_maintenance_tasks),
                    "total_google_reviews": int(row.total_google_reviews),
                    "total_cash_deposit": float(row.total_cash_deposit),
                }
            )

        summary = {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": (end_date - start_date).days + 1,
            "records_count": sum(item["records_count"] for item in daily),
            "total_checkins": sum(item["total_checkins"] for item in daily),
            "total_checkouts": sum(item["total_checkouts"] for item in daily),
            "total_complaints": sum(item["total_complaints"] for item in daily),
            "total_maintenance_tasks": sum(item["total_maintenance_tasks"] for item in daily),
            "total_google_reviews": sum(item["total_google_reviews"] for item in daily),
            "total_cash_deposit": round(sum(item["total_cash_deposit"] for item in daily), 2),
        }

        return {
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "property_id": property_id,
            "summary": summary,
            "daily": daily,
        }

    async def update_daily_kra(
        self,
        kra: DailyKRA,
        update_data: DailyKRAUpdate,
    ) -> DailyKRA:
        """
        Update daily KRA

        Args:
            kra: DailyKRA object to update
            update_data: Update data

        Returns:
            Updated DailyKRA object
        """
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(kra, field, value)

        await self.db.flush()
        return kra

    async def delete_daily_kra(self, kra: DailyKRA) -> None:
        """
        Soft delete daily KRA

        Args:
            kra: DailyKRA object to delete
        """
        kra.soft_delete()
        await self.db.flush()


class WeeklyKRAService:
    """Service for weekly KRA operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize weekly KRA service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def create_weekly_kra(
        self,
        tenant_id: int,
        user_id: int,
        kra_data: WeeklyKRACreate,
    ) -> WeeklyKRA:
        """
        Create new weekly KRA

        Args:
            tenant_id: Tenant ID for multi-tenancy
            user_id: User ID creating the KRA
            kra_data: Weekly KRA data

        Returns:
            Created WeeklyKRA object
        """
        db_kra = WeeklyKRA(
            tenant_id=tenant_id,
            user_id=user_id,
            week_starting_date=kra_data.week_starting_date,
            year=kra_data.year,
            week_number=kra_data.week_number,
            ota_images_uploaded=kra_data.ota_images_uploaded,
            ota_platforms=kra_data.ota_platforms,
            supply_stock_reviewed=kra_data.supply_stock_reviewed,
            supply_notes=kra_data.supply_notes,
            notes=kra_data.notes,
            is_submitted=True,
        )
        self.db.add(db_kra)
        await self.db.flush()
        return db_kra

    async def get_weekly_kra_by_id(
        self,
        kra_id: int,
        tenant_id: int,
    ) -> Optional[WeeklyKRA]:
        """
        Get weekly KRA by ID with tenant filtering

        Args:
            kra_id: KRA ID to retrieve
            tenant_id: Tenant ID for filtering

        Returns:
            WeeklyKRA object if found and belongs to tenant, None otherwise
        """
        result = await self.db.execute(
            select(WeeklyKRA).where(
                and_(
                    WeeklyKRA.id == kra_id,
                    WeeklyKRA.tenant_id == tenant_id,
                    WeeklyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_weekly_kra_by_week(
        self,
        tenant_id: int,
        user_id: int,
        year: int,
        week_number: int,
    ) -> Optional[WeeklyKRA]:
        """
        Get weekly KRA for specific week and user

        Args:
            tenant_id: Tenant ID for filtering
            user_id: User ID for filtering
            year: Year
            week_number: ISO week number

        Returns:
            WeeklyKRA object if found, None otherwise
        """
        result = await self.db.execute(
            select(WeeklyKRA).where(
                and_(
                    WeeklyKRA.tenant_id == tenant_id,
                    WeeklyKRA.user_id == user_id,
                    WeeklyKRA.year == year,
                    WeeklyKRA.week_number == week_number,
                    WeeklyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_weekly_kras(
        self,
        tenant_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[list[WeeklyKRA], int]:
        """
        List weekly KRAs with tenant filtering

        Args:
            tenant_id: Tenant ID for filtering
            user_id: Optional user ID to filter by specific user
            skip: Number of records to skip
            limit: Number of records to return

        Returns:
            Tuple of (list of WeeklyKRA objects, total count)
        """
        query = select(WeeklyKRA).where(
            and_(
                WeeklyKRA.tenant_id == tenant_id,
                WeeklyKRA.deleted_at.is_(None),
            )
        )

        if user_id:
            query = query.where(WeeklyKRA.user_id == user_id)

        count_query = select(func.count()).select_from(WeeklyKRA).where(
            and_(
                WeeklyKRA.tenant_id == tenant_id,
                WeeklyKRA.deleted_at.is_(None),
            )
        )
        if user_id:
            count_query = count_query.where(WeeklyKRA.user_id == user_id)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Get paginated results
        result = await self.db.execute(
            query.order_by(desc(WeeklyKRA.week_starting_date))
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all(), total

    async def update_weekly_kra(
        self,
        kra: WeeklyKRA,
        update_data: WeeklyKRAUpdate,
    ) -> WeeklyKRA:
        """
        Update weekly KRA

        Args:
            kra: WeeklyKRA object to update
            update_data: Update data

        Returns:
            Updated WeeklyKRA object
        """
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(kra, field, value)

        await self.db.flush()
        return kra

    async def delete_weekly_kra(self, kra: WeeklyKRA) -> None:
        """
        Soft delete weekly KRA

        Args:
            kra: WeeklyKRA object to delete
        """
        kra.soft_delete()
        await self.db.flush()


class MonthlyKRAService:
    """Service for monthly KRA operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize monthly KRA service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def create_monthly_kra(
        self,
        tenant_id: int,
        user_id: int,
        kra_data: MonthlyKRACreate,
    ) -> MonthlyKRA:
        """
        Create new monthly KRA

        Args:
            tenant_id: Tenant ID for multi-tenancy
            user_id: User ID creating the KRA
            kra_data: Monthly KRA data

        Returns:
            Created MonthlyKRA object
        """
        db_kra = MonthlyKRA(
            tenant_id=tenant_id,
            user_id=user_id,
            month=kra_data.month,
            year=kra_data.year,
            revenue_report_url=kra_data.revenue_report_url,
            notes=kra_data.notes,
            is_submitted=True,
        )
        self.db.add(db_kra)
        await self.db.flush()
        return db_kra

    async def get_monthly_kra_by_id(
        self,
        kra_id: int,
        tenant_id: int,
    ) -> Optional[MonthlyKRA]:
        """
        Get monthly KRA by ID with tenant filtering

        Args:
            kra_id: KRA ID to retrieve
            tenant_id: Tenant ID for filtering

        Returns:
            MonthlyKRA object if found and belongs to tenant, None otherwise
        """
        result = await self.db.execute(
            select(MonthlyKRA).where(
                and_(
                    MonthlyKRA.id == kra_id,
                    MonthlyKRA.tenant_id == tenant_id,
                    MonthlyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_monthly_kra_by_month(
        self,
        tenant_id: int,
        user_id: int,
        month: int,
        year: int,
    ) -> Optional[MonthlyKRA]:
        """
        Get monthly KRA for specific month and user

        Args:
            tenant_id: Tenant ID for filtering
            user_id: User ID for filtering
            month: Month (1-12)
            year: Year

        Returns:
            MonthlyKRA object if found, None otherwise
        """
        result = await self.db.execute(
            select(MonthlyKRA).where(
                and_(
                    MonthlyKRA.tenant_id == tenant_id,
                    MonthlyKRA.user_id == user_id,
                    MonthlyKRA.month == month,
                    MonthlyKRA.year == year,
                    MonthlyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_monthly_kras(
        self,
        tenant_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[list[MonthlyKRA], int]:
        """
        List monthly KRAs with tenant filtering

        Args:
            tenant_id: Tenant ID for filtering
            user_id: Optional user ID to filter by specific user
            skip: Number of records to skip
            limit: Number of records to return

        Returns:
            Tuple of (list of MonthlyKRA objects, total count)
        """
        query = select(MonthlyKRA).where(
            and_(
                MonthlyKRA.tenant_id == tenant_id,
                MonthlyKRA.deleted_at.is_(None),
            )
        )

        if user_id:
            query = query.where(MonthlyKRA.user_id == user_id)

        count_query = select(func.count()).select_from(MonthlyKRA).where(
            and_(
                MonthlyKRA.tenant_id == tenant_id,
                MonthlyKRA.deleted_at.is_(None),
            )
        )
        if user_id:
            count_query = count_query.where(MonthlyKRA.user_id == user_id)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Get paginated results
        result = await self.db.execute(
            query.order_by(desc(MonthlyKRA.year), desc(MonthlyKRA.month))
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all(), total

    async def update_monthly_kra(
        self,
        kra: MonthlyKRA,
        update_data: MonthlyKRAUpdate,
    ) -> MonthlyKRA:
        """
        Update monthly KRA

        Args:
            kra: MonthlyKRA object to update
            update_data: Update data

        Returns:
            Updated MonthlyKRA object
        """
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(kra, field, value)

        await self.db.flush()
        return kra

    async def delete_monthly_kra(self, kra: MonthlyKRA) -> None:
        """
        Soft delete monthly KRA

        Args:
            kra: MonthlyKRA object to delete
        """
        kra.soft_delete()
        await self.db.flush()


class QuarterlyKRAService:
    """Service for quarterly KRA operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize quarterly KRA service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def create_quarterly_kra(
        self,
        tenant_id: int,
        user_id: int,
        kra_data: QuarterlyKRACreate,
    ) -> QuarterlyKRA:
        """
        Create new quarterly KRA

        Args:
            tenant_id: Tenant ID for multi-tenancy
            user_id: User ID creating the KRA
            kra_data: Quarterly KRA data

        Returns:
            Created QuarterlyKRA object
        """
        db_kra = QuarterlyKRA(
            tenant_id=tenant_id,
            user_id=user_id,
            quarter=kra_data.quarter,
            year=kra_data.year,
            revenue_report_url=kra_data.revenue_report_url,
            notes=kra_data.notes,
            is_submitted=True,
        )
        self.db.add(db_kra)
        await self.db.flush()
        return db_kra

    async def get_quarterly_kra_by_id(
        self,
        kra_id: int,
        tenant_id: int,
    ) -> Optional[QuarterlyKRA]:
        """
        Get quarterly KRA by ID with tenant filtering

        Args:
            kra_id: KRA ID to retrieve
            tenant_id: Tenant ID for filtering

        Returns:
            QuarterlyKRA object if found and belongs to tenant, None otherwise
        """
        result = await self.db.execute(
            select(QuarterlyKRA).where(
                and_(
                    QuarterlyKRA.id == kra_id,
                    QuarterlyKRA.tenant_id == tenant_id,
                    QuarterlyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_quarterly_kra_by_quarter(
        self,
        tenant_id: int,
        user_id: int,
        quarter: int,
        year: int,
    ) -> Optional[QuarterlyKRA]:
        """
        Get quarterly KRA for specific quarter and user

        Args:
            tenant_id: Tenant ID for filtering
            user_id: User ID for filtering
            quarter: Quarter (1-4)
            year: Year

        Returns:
            QuarterlyKRA object if found, None otherwise
        """
        result = await self.db.execute(
            select(QuarterlyKRA).where(
                and_(
                    QuarterlyKRA.tenant_id == tenant_id,
                    QuarterlyKRA.user_id == user_id,
                    QuarterlyKRA.quarter == quarter,
                    QuarterlyKRA.year == year,
                    QuarterlyKRA.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_quarterly_kras(
        self,
        tenant_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[list[QuarterlyKRA], int]:
        """
        List quarterly KRAs with tenant filtering

        Args:
            tenant_id: Tenant ID for filtering
            user_id: Optional user ID to filter by specific user
            skip: Number of records to skip
            limit: Number of records to return

        Returns:
            Tuple of (list of QuarterlyKRA objects, total count)
        """
        query = select(QuarterlyKRA).where(
            and_(
                QuarterlyKRA.tenant_id == tenant_id,
                QuarterlyKRA.deleted_at.is_(None),
            )
        )

        if user_id:
            query = query.where(QuarterlyKRA.user_id == user_id)

        count_query = select(func.count()).select_from(QuarterlyKRA).where(
            and_(
                QuarterlyKRA.tenant_id == tenant_id,
                QuarterlyKRA.deleted_at.is_(None),
            )
        )
        if user_id:
            count_query = count_query.where(QuarterlyKRA.user_id == user_id)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Get paginated results
        result = await self.db.execute(
            query.order_by(desc(QuarterlyKRA.year), desc(QuarterlyKRA.quarter))
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all(), total

    async def update_quarterly_kra(
        self,
        kra: QuarterlyKRA,
        update_data: QuarterlyKRAUpdate,
    ) -> QuarterlyKRA:
        """
        Update quarterly KRA

        Args:
            kra: QuarterlyKRA object to update
            update_data: Update data

        Returns:
            Updated QuarterlyKRA object
        """
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(kra, field, value)

        await self.db.flush()
        return kra

    async def delete_quarterly_kra(self, kra: QuarterlyKRA) -> None:
        """
        Soft delete quarterly KRA

        Args:
            kra: QuarterlyKRA object to delete
        """
        kra.soft_delete()
        await self.db.flush()
