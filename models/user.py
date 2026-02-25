from sqlalchemy import Column, String, Boolean
from models.base import BaseModel

class User(BaseModel):
    __tablename__ = "users"
    
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="staff") # roles: owner, remote_ops, staff
    is_active = Column(Boolean, default=True)
