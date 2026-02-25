"""
Property Service

Handles property management business logic.
CRUD operations and property-related queries.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.property import Property
from app.schemas.property import PropertyCreate, PropertyUpdate


class PropertyService:
    """Service for property operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize property service with database session

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def get_property_by_id(self, property_id: int) -> Optional[Property]:
        """
        Get property by ID

        Args:
            property_id: Property ID to retrieve

        Returns:
            Property object if found, None otherwise
        """
        result = await self.db.execute(
            select(Property).where(Property.id == property_id)
        )
        return result.scalar_one_or_none()

    async def get_property_by_code(self, code: str) -> Optional[Property]:
        """
        Get property by code

        Args:
            code: Property code to search for

        Returns:
            Property object if found, None otherwise
        """
        result = await self.db.execute(
            select(Property).where(Property.code == code)
        )
        return result.scalar_one_or_none()

    async def create_property(self, property_data: PropertyCreate) -> Property:
        """
        Create new property

        Args:
            property_data: PropertyCreate schema with property details

        Returns:
            Created Property object
        """
        property_obj = Property(**property_data.dict())
        self.db.add(property_obj)
        await self.db.commit()
        await self.db.refresh(property_obj)
        return property_obj

    async def update_property(
        self, property_obj: Property, update_data: PropertyUpdate
    ) -> Property:
        """
        Update existing property

        Args:
            property_obj: Property object to update
            update_data: PropertyUpdate schema with new values

        Returns:
            Updated Property object
        """
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(property_obj, field, value)

        await self.db.commit()
        await self.db.refresh(property_obj)
        return property_obj

    async def delete_property(self, property_obj: Property) -> None:
        """
        Soft delete property (deactivate)

        Args:
            property_obj: Property object to delete
        """
        property_obj.is_active = False
        await self.db.commit()

    async def list_properties(
        self, skip: int = 0, limit: int = 20, only_active: bool = True
    ) -> tuple[list[Property], int]:
        """
        List properties with pagination

        Args:
            skip: Number of records to skip
            limit: Number of records to return
            only_active: If True, only return active properties

        Returns:
            Tuple of (properties list, total count)
        """
        query = select(Property)
        if only_active:
            query = query.where(Property.is_active == True)

        # Get total count
        count_query = query.count()
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()

        # Get paginated results
        result = await self.db.execute(
            query.offset(skip).limit(limit)
        )
        properties = result.scalars().all()
        return properties, total

    async def get_properties_by_city(self, city: str) -> list[Property]:
        """
        Get all properties in a specific city

        Args:
            city: City name to filter by

        Returns:
            List of Property objects in the specified city
        """
        result = await self.db.execute(
            select(Property).where(Property.city == city).where(Property.is_active == True)
        )
        return result.scalars().all()
