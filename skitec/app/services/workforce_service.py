"""
Workforce Service

Handles workforce management business logic.
CRUD operations for employees and workforce entries.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.workforce import WorkforceEntry
from app.schemas.workforce import WorkforceCreate, WorkforceUpdate


class WorkforceService:
    """Service for workforce operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize workforce service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def get_workforce_entry(self, entry_id: int) -> Optional[WorkforceEntry]:
        """
        Get workforce entry by ID

        Args:
            entry_id: Workforce entry ID

        Returns:
            WorkforceEntry object if found, None otherwise
        """
        result = await self.db.execute(
            select(WorkforceEntry).where(WorkforceEntry.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def get_by_employee_id(self, employee_id: str) -> Optional[WorkforceEntry]:
        """
        Get workforce entry by employee ID

        Args:
            employee_id: Employee ID string

        Returns:
            WorkforceEntry object if found, None otherwise
        """
        result = await self.db.execute(
            select(WorkforceEntry).where(WorkforceEntry.employee_id == employee_id)
        )
        return result.scalar_one_or_none()

    async def create_workforce_entry(self, entry_data: WorkforceCreate) -> WorkforceEntry:
        """
        Create new workforce entry

        Args:
            entry_data: WorkforceCreate schema

        Returns:
            Created WorkforceEntry object
        """
        entry = WorkforceEntry(**entry_data.dict())
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def update_workforce_entry(
        self, entry: WorkforceEntry, update_data: WorkforceUpdate
    ) -> WorkforceEntry:
        """
        Update workforce entry

        Args:
            entry: WorkforceEntry to update
            update_data: WorkforceUpdate schema

        Returns:
            Updated WorkforceEntry
        """
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(entry, field, value)

        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete_workforce_entry(self, entry: WorkforceEntry) -> None:
        """
        Soft delete workforce entry (deactivate)

        Args:
            entry: WorkforceEntry to delete
        """
        entry.is_active = False
        await self.db.commit()

    async def list_by_property(
        self, property_id: int, skip: int = 0, limit: int = 20
    ) -> tuple[list[WorkforceEntry], int]:
        """
        List workforce entries for a property

        Args:
            property_id: Property ID to filter by
            skip: Number to skip
            limit: Number to return

        Returns:
            Tuple of (list[WorkforceEntry], total_count)
        """
        query = select(WorkforceEntry).where(
            WorkforceEntry.property_id == property_id
        )

        count_result = await self.db.execute(query.count())
        total = count_result.scalar()

        result = await self.db.execute(
            query.offset(skip).limit(limit)
        )
        entries = result.scalars().all()
        return entries, total

    async def list_by_department(self, department: str) -> list[WorkforceEntry]:
        """
        List all workforce entries in a department

        Args:
            department: Department name

        Returns:
            List of WorkforceEntry objects
        """
        result = await self.db.execute(
            select(WorkforceEntry)
            .where(WorkforceEntry.department == department)
            .where(WorkforceEntry.is_active == True)
        )
        return result.scalars().all()
