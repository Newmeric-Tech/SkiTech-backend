from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from crud.base import CRUDBase
from models.sop import SOPCategory, SOPItem

# --- SOP Category Schemas ---
class SOPCategoryBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class SOPCategoryCreate(SOPCategoryBase):
    name: str

class SOPCategoryUpdate(SOPCategoryBase):
    pass

class SOPCategoryInDB(SOPCategoryBase):
    id: int
    tenant_id: str
    property_id: str

    class Config:
        from_attributes = True

# --- SOP Item Schemas ---
class SOPItemBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category_id: Optional[int] = None

class SOPItemCreate(SOPItemBase):
    title: str
    content: str
    category_id: int

class SOPItemUpdate(SOPItemBase):
    pass

class SOPItemInDB(SOPItemBase):
    id: int
    tenant_id: str
    property_id: str

    class Config:
        from_attributes = True

# --- CRUD Operations ---
class CRUDSOPCategory(CRUDBase[SOPCategory, SOPCategoryCreate, SOPCategoryUpdate]):
    pass

class CRUDSOPItem(CRUDBase[SOPItem, SOPItemCreate, SOPItemUpdate]):
    def get_by_category(self, db: Session, *, category_id: int, tenant_id: str) -> List[SOPItem]:
        return db.query(SOPItem).filter(
            SOPItem.category_id == category_id,
            SOPItem.tenant_id == tenant_id
        ).all()

sop_category = CRUDSOPCategory(SOPCategory)
sop_item = CRUDSOPItem(SOPItem)
