"""
Seed script to insert default roles into the database
"""
import asyncio
from app.core.database import engine
from app.models.base import Base
from app.models.models import Role
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Define default roles with hierarchy (lower level = higher privilege)
DEFAULT_ROLES = [
    {"name": "Super Admin", "role_level": 0, "description": "System administrator with full access"},
    {"name": "Tenant Admin", "role_level": 1, "description": "Tenant administrator"},
    {"name": "Manager", "role_level": 2, "description": "Property/Department manager"},
    {"name": "Staff", "role_level": 3, "description": "Regular staff member"},
]

async def seed_roles():
    """Insert default roles into database"""
    AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        for role_data in DEFAULT_ROLES:
            # Check if role already exists
            existing = await session.execute(
                __import__("sqlalchemy").select(Role).where(Role.name == role_data["name"])
            )
            if existing.scalar_one_or_none():
                print(f"✓ Role '{role_data['name']}' already exists")
                continue
            
            # Create new role
            role = Role(
                name=role_data["name"],
                role_level=role_data["role_level"],
                description=role_data["description"]
            )
            session.add(role)
            print(f"✓ Created role '{role_data['name']}'")
        
        await session.commit()
        print("\n✓ All default roles seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_roles())
