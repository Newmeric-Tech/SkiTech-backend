"""
Base repository class for database access patterns.
All chat repositories inherit from this to enforce multi-tenant isolation.
"""

from typing import Any, Generic, List, Optional, Type, TypeVar
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T", bound=DeclarativeBase)


class BaseRepository(Generic[T]):
    """
    Generic repository for CRUD operations with multi-tenant support.
    All queries automatically filter by tenant_id and property_id.
    """

    def __init__(self, session: AsyncSession, model_class: Type[T]):
        self.session = session
        self.model_class = model_class

    async def create(self, obj_in: dict, tenant_id: UUID, **kwargs) -> T:
        """Create a new record."""
        db_obj = self.model_class(**obj_in, tenant_id=tenant_id, **kwargs)
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def get_by_id(
        self,
        obj_id: UUID,
        tenant_id: UUID,
        property_id: Optional[UUID] = None,
    ) -> Optional[T]:
        """Get a single record by ID with tenant validation."""
        filters = [
            self.model_class.id == obj_id,
            self.model_class.tenant_id == tenant_id,
        ]
        
        # If property_id is part of model, add to filter
        if property_id and hasattr(self.model_class, "property_id"):
            filters.append(self.model_class.property_id == property_id)
        
        query = select(self.model_class).where(and_(*filters))
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_all(
        self,
        tenant_id: UUID,
        property_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[T], int]:
        """Get all records for a tenant with pagination."""
        filters = [self.model_class.tenant_id == tenant_id]
        
        if property_id and hasattr(self.model_class, "property_id"):
            filters.append(self.model_class.property_id == property_id)
        
        # Get total count
        count_query = select(self.model_class).where(and_(*filters))
        count_result = await self.session.execute(count_query)
        total = len(count_result.scalars().all())
        
        # Get paginated results
        query = (
            select(self.model_class)
            .where(and_(*filters))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all(), total

    async def update(
        self,
        obj_id: UUID,
        obj_in: dict,
        tenant_id: UUID,
        property_id: Optional[UUID] = None,
    ) -> Optional[T]:
        """Update a record."""
        db_obj = await self.get_by_id(obj_id, tenant_id, property_id)
        if not db_obj:
            return None
        
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def delete(
        self,
        obj_id: UUID,
        tenant_id: UUID,
        property_id: Optional[UUID] = None,
    ) -> bool:
        """Delete a record."""
        db_obj = await self.get_by_id(obj_id, tenant_id, property_id)
        if not db_obj:
            return False
        
        await self.session.delete(db_obj)
        await self.session.flush()
        return True

    async def _fetch_with_filters(
        self,
        filters: List[Any],
        skip: int = 0,
        limit: int = 20,
        order_by=None,
    ) -> tuple[List[T], int]:
        """
        Helper to fetch records with custom filters.
        Used by subclasses for complex queries.
        """
        # Get total count
        count_query = select(self.model_class).where(and_(*filters))
        count_result = await self.session.execute(count_query)
        total = len(count_result.scalars().all())
        
        # Get paginated results
        query = select(self.model_class).where(and_(*filters))
        if order_by is not None:
            query = query.order_by(order_by)
        query = query.offset(skip).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all(), total
