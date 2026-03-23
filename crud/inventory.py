from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from crud.base import CRUDBase
from models.inventory import InventoryItem

# --- Inventory Item Schemas ---
class InventoryItemBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[int] = 0
    sku: Optional[str] = None
    price: Optional[float] = None

class InventoryItemCreate(InventoryItemBase):
    name: str
    quantity: int

class InventoryItemUpdate(InventoryItemBase):
    pass

class InventoryItemInDB(InventoryItemBase):
    id: int
    tenant_id: str
    property_id: str

    class Config:
        from_attributes = True

# --- CRUD Operations ---
class CRUDInventoryItem(CRUDBase[InventoryItem, InventoryItemCreate, InventoryItemUpdate]):
    def get_multi_by_property(
        self, db: Session, *, tenant_id: str, property_id: Optional[str] = None, skip: int = 0, limit: int = 100
    ) -> List[InventoryItem]:
        query = db.query(self.model).filter(self.model.tenant_id == tenant_id)
        if property_id:
            query = query.filter(self.model.property_id == property_id)
        return query.offset(skip).limit(limit).all()

inventory_item = CRUDInventoryItem(InventoryItem)
