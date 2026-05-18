"""
Seed script to create a default tenant
"""
import asyncio
import uuid
from app.core.database import engine
from app.models.models import Tenant
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

async def seed_tenant():
    """Create a default tenant for testing"""
    AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        # Check if any tenant exists
        existing = await session.execute(
            __import__("sqlalchemy").select(Tenant)
        )
        if existing.scalar_one_or_none():
            print("✓ Tenant already exists")
            result = await session.execute(__import__("sqlalchemy").select(Tenant))
            tenant = result.scalar_one()
            print(f"  Tenant ID: {tenant.id}")
            print(f"  Name: {tenant.business_name}")
            return
        
        # Create default tenant
        tenant = Tenant(
            business_name="SkiTech Demo Hotel",
            business_type="hotel",
            owner_name="Demo Owner",
            contact_email="admin@skitech.local",
            contact_phone="+1-800-SKITECH",
            subscription_status="active",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        
        print("✓ Default tenant created successfully!")
        print(f"  Tenant ID: {tenant.id}")
        print(f"  Name: {tenant.business_name}")
        print(f"\nUse this tenant_id for registration:")
        print(f"  {tenant.id}")

if __name__ == "__main__":
    asyncio.run(seed_tenant())
