from sqlalchemy.orm import Session
from typing import Optional
from models.tenant import Tenant
from crud.tenant import tenant as crud_tenant
from repositories.base import BaseRepository

class TenantRepository(BaseRepository):
    def __init__(self):
        super().__init__(crud_tenant)

    def get_by_slug(self, db: Session, slug: str) -> Optional[Tenant]:
        return self.crud.get_by_slug(db, slug)

tenant_repo = TenantRepository()
