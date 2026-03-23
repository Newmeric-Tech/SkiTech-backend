from sqlalchemy import Column, Integer, String, Text, Float
from models.base import BaseModel

class InventoryItem(BaseModel):
    __tablename__ = "inventory_items"

    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Integer, default=0)
    sku = Column(String, index=True, nullable=True)
    price = Column(Float, nullable=True)
