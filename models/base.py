from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, String
from db_connection import Base

class BaseModel(Base):
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)  # Owner/Client ID
    property_id = Column(String, index=True, nullable=False) # Specific Hotel ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
