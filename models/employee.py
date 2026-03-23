from sqlalchemy import Column, String, Boolean
from models.base import BaseModel

class Employee(BaseModel):
    __tablename__ = "employees"
    
    full_name = Column(String, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, nullable=False) # e.g., Manager, Staff, etc.
    is_active = Column(Boolean, default=True)
    employee_id = Column(String, unique=True, index=True, nullable=False) # Internal ID
