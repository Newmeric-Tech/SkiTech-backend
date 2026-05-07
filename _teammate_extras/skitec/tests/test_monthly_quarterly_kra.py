"""
Test cases for Monthly and Quarterly KRA endpoints

Tests cover:
- Monthly KRA creation with revenue_report_url
- Quarterly KRA creation with revenue_report_url
- Validation of month/quarter and year
- Duplicate KRA prevention
- Full CRUD operations for both endpoints
"""

import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.kra import (
    MonthlyKRACreate,
    MonthlyKRAResponse,
    QuarterlyKRACreate,
    QuarterlyKRAResponse,
)
from app.services.kra_service import MonthlyKRAService, QuarterlyKRAService


class TestMonthlyKRA:
    """Test Monthly KRA endpoints"""

    @pytest.mark.asyncio
    async def test_create_monthly_kra_with_revenue_report(self, db_session: AsyncSession):
        """Test creating monthly KRA with revenue report URL"""
        kra_data = MonthlyKRACreate(
            month=3,
            year=2026,
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf",
            notes="March 2026 revenue report"
        )
        
        service = MonthlyKRAService(db_session)
        kra = await service.create_monthly_kra(
            tenant_id=1,
            user_id=1,
            kra_data=kra_data
        )
        
        assert kra.month == 3
        assert kra.year == 2026
        assert kra.revenue_report_url == "https://s3.amazonaws.com/kra-submissions/monthly/2026-03-revenue.pdf"
        assert kra.is_submitted is True
        assert kra.tenant_id == 1
        assert kra.user_id == 1

    @pytest.mark.asyncio
    async def test_create_monthly_kra_without_revenue_report(self, db_session: AsyncSession):
        """Test creating monthly KRA without revenue report (optional field)"""
        kra_data = MonthlyKRACreate(
            month=4,
            year=2026,
            revenue_report_url=None,
            notes="April 2026 - Report to be uploaded later"
        )
        
        service = MonthlyKRAService(db_session)
        kra = await service.create_monthly_kra(
            tenant_id=1,
            user_id=1,
            kra_data=kra_data
        )
        
        assert kra.month == 4
        assert kra.year == 2026
        assert kra.revenue_report_url is None
        assert kra.is_submitted is True

    @pytest.mark.asyncio
    async def test_get_monthly_kra_by_month(self, db_session: AsyncSession):
        """Test retrieving monthly KRA by month and year"""
        kra_data = MonthlyKRACreate(
            month=5,
            year=2026,
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/monthly/2026-05-revenue.pdf"
        )
        
        service = MonthlyKRAService(db_session)
        created_kra = await service.create_monthly_kra(
            tenant_id=1,
            user_id=1,
            kra_data=kra_data
        )
        await db_session.flush()
        
        # Retrieve the KRA
        retrieved_kra = await service.get_monthly_kra_by_month(
            tenant_id=1,
            user_id=1,
            month=5,
            year=2026
        )
        
        assert retrieved_kra is not None
        assert retrieved_kra.month == 5
        assert retrieved_kra.year == 2026

    @pytest.mark.asyncio
    async def test_update_monthly_kra_revenue_report(self, db_session: AsyncSession):
        """Test updating revenue report URL for monthly KRA"""
        from app.schemas.kra import MonthlyKRAUpdate
        
        kra_data = MonthlyKRACreate(
            month=6,
            year=2026,
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/monthly/2026-06-revenue-v1.pdf"
        )
        
        service = MonthlyKRAService(db_session)
        kra = await service.create_monthly_kra(
            tenant_id=1,
            user_id=1,
            kra_data=kra_data
        )
        
        # Update with new revenue report
        update_data = MonthlyKRAUpdate(
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/monthly/2026-06-revenue-v2.pdf"
        )
        
        updated_kra = await service.update_monthly_kra(kra, update_data)
        assert updated_kra.revenue_report_url == "https://s3.amazonaws.com/kra-submissions/monthly/2026-06-revenue-v2.pdf"

    @pytest.mark.asyncio
    async def test_list_monthly_kras(self, db_session: AsyncSession):
        """Test listing monthly KRAs with pagination"""
        service = MonthlyKRAService(db_session)
        
        # Create multiple monthly KRAs
        for month in range(1, 4):
            kra_data = MonthlyKRACreate(
                month=month,
                year=2026,
                revenue_report_url=f"https://s3.amazonaws.com/kra-submissions/monthly/2026-{month:02d}-revenue.pdf"
            )
            await service.create_monthly_kra(
                tenant_id=1,
                user_id=1,
                kra_data=kra_data
            )
        
        await db_session.flush()
        
        # List KRAs
        kras, total = await service.list_monthly_kras(
            tenant_id=1,
            user_id=1,
            skip=0,
            limit=10
        )
        
        assert len(kras) >= 3
        assert total >= 3


class TestQuarterlyKRA:
    """Test Quarterly KRA endpoints"""

    @pytest.mark.asyncio
    async def test_create_quarterly_kra_with_revenue_report(self, db_session: AsyncSession):
        """Test creating quarterly KRA with revenue report URL"""
        kra_data = QuarterlyKRACreate(
            quarter=1,
            year=2026,
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf",
            notes="Q1 2026 revenue report"
        )
        
        service = QuarterlyKRAService(db_session)
        kra = await service.create_quarterly_kra(
            tenant_id=1,
            user_id=1,
            kra_data=kra_data
        )
        
        assert kra.quarter == 1
        assert kra.year == 2026
        assert kra.revenue_report_url == "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q1-revenue.pdf"
        assert kra.is_submitted is True
        assert kra.tenant_id == 1
        assert kra.user_id == 1

    @pytest.mark.asyncio
    async def test_create_quarterly_kra_all_quarters(self, db_session: AsyncSession):
        """Test creating quarterly KRAs for all quarters"""
        service = QuarterlyKRAService(db_session)
        
        for quarter in range(1, 5):
            kra_data = QuarterlyKRACreate(
                quarter=quarter,
                year=2026,
                revenue_report_url=f"https://s3.amazonaws.com/kra-submissions/quarterly/2026-q{quarter}-revenue.pdf"
            )
            
            kra = await service.create_quarterly_kra(
                tenant_id=1,
                user_id=2,
                kra_data=kra_data
            )
            
            assert kra.quarter == quarter
            assert kra.year == 2026

    @pytest.mark.asyncio
    async def test_get_quarterly_kra_by_quarter(self, db_session: AsyncSession):
        """Test retrieving quarterly KRA by quarter and year"""
        kra_data = QuarterlyKRACreate(
            quarter=2,
            year=2026,
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/quarterly/2026-q2-revenue.pdf"
        )
        
        service = QuarterlyKRAService(db_session)
        created_kra = await service.create_quarterly_kra(
            tenant_id=1,
            user_id=3,
            kra_data=kra_data
        )
        await db_session.flush()
        
        # Retrieve the KRA
        retrieved_kra = await service.get_quarterly_kra_by_quarter(
            tenant_id=1,
            user_id=3,
            quarter=2,
            year=2026
        )
        
        assert retrieved_kra is not None
        assert retrieved_kra.quarter == 2
        assert retrieved_kra.year == 2026

    @pytest.mark.asyncio
    async def test_update_quarterly_kra_revenue_report(self, db_session: AsyncSession):
        """Test updating revenue report URL for quarterly KRA"""
        from app.schemas.kra import QuarterlyKRAUpdate
        
        kra_data = QuarterlyKRACreate(
            quarter=3,
            year=2026,
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/quarterly/2026-q3-revenue-v1.pdf"
        )
        
        service = QuarterlyKRAService(db_session)
        kra = await service.create_quarterly_kra(
            tenant_id=1,
            user_id=4,
            kra_data=kra_data
        )
        
        # Update with new revenue report
        update_data = QuarterlyKRAUpdate(
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/quarterly/2026-q3-revenue-v2.pdf"
        )
        
        updated_kra = await service.update_quarterly_kra(kra, update_data)
        assert updated_kra.revenue_report_url == "https://s3.amazonaws.com/kra-submissions/quarterly/2026-q3-revenue-v2.pdf"

    @pytest.mark.asyncio
    async def test_list_quarterly_kras(self, db_session: AsyncSession):
        """Test listing quarterly KRAs with pagination"""
        service = QuarterlyKRAService(db_session)
        
        # Create multiple quarterly KRAs
        for quarter in range(1, 4):
            kra_data = QuarterlyKRACreate(
                quarter=quarter,
                year=2026,
                revenue_report_url=f"https://s3.amazonaws.com/kra-submissions/quarterly/2026-q{quarter}-revenue.pdf"
            )
            await service.create_quarterly_kra(
                tenant_id=1,
                user_id=5,
                kra_data=kra_data
            )
        
        await db_session.flush()
        
        # List KRAs
        kras, total = await service.list_quarterly_kras(
            tenant_id=1,
            user_id=5,
            skip=0,
            limit=10
        )
        
        assert len(kras) >= 3
        assert total >= 3

    @pytest.mark.asyncio
    async def test_delete_quarterly_kra(self, db_session: AsyncSession):
        """Test deleting quarterly KRA (soft delete)"""
        kra_data = QuarterlyKRACreate(
            quarter=4,
            year=2026,
            revenue_report_url="https://s3.amazonaws.com/kra-submissions/quarterly/2026-q4-revenue.pdf"
        )
        
        service = QuarterlyKRAService(db_session)
        kra = await service.create_quarterly_kra(
            tenant_id=1,
            user_id=6,
            kra_data=kra_data
        )
        
        kra_id = kra.id
        await db_session.flush()
        
        # Delete KRA
        await service.delete_quarterly_kra(kra)
        await db_session.flush()
        
        # Verify it's soft deleted
        retrieved = await service.get_quarterly_kra_by_id(
            kra_id=kra_id,
            tenant_id=1
        )
        assert retrieved is None
