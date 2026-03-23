from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from models.base import BaseModel

class SOPCategory(BaseModel):
    __tablename__ = "sop_categories"

    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)

    items = relationship("SOPItem", back_populates="category", cascade="all, delete-orphan")

class SOPItem(BaseModel):
    __tablename__ = "sop_items"

    category_id = Column(Integer, ForeignKey("sop_categories.id"), nullable=False)
    title = Column(String, index=True, nullable=False)
    content = Column(Text, nullable=False)

    category = relationship("SOPCategory", back_populates="items")
