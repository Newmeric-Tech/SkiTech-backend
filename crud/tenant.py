from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from crud.base import CRUDBase
from models.tenant import Tenant

class TenantCreate(BaseModel):
    name: str
    slug: str
    subscription_plan: Optional[str] = "basic"

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    subscription_plan: Optional[str] = None

class CRUDTenant(CRUDBase[Tenant, TenantCreate, TenantUpdate]):
    def get_by_slug(self, db: Session, slug: str) -> Optional[Tenant]:
        return db.query(Tenant).filter(Tenant.slug == slug).first()

tenant = CRUDTenant(Tenant)
