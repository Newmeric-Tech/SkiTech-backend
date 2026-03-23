from sqlalchemy import Column, String, Boolean
from models.base import BaseModel

class Tenant(BaseModel):
    __tablename__ = "tenants"
    
    name = Column(String, index=True, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    subscription_plan = Column(String, default="basic")
