from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base

class Integration(Base):
    __tablename__ = 'integrations'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tenant_id = Column(UUID(as_uuid=True), nullable=False)  # References tenants.id
    property_id = Column(UUID(as_uuid=True), nullable=False)  # References properties.id
    provider_name = Column(String(50), nullable=False)  # 'channex' | 'mews' | 'cloudbeds' | 'siteminder' | 'little_hotelier'
    credentials_json = Column(Text, nullable=False)  # AES-256-GCM encrypted JSON string
    connection_status = Column(String(20), nullable=False, default='pending')  # 'active' | 'error' | 'disconnected' | 'pending'
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('property_id', 'provider_name', name='uq_property_provider'),
    )


class SyncLog(Base):
    __tablename__ = 'sync_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    integration_id = Column(UUID(as_uuid=True), ForeignKey('integrations.id', ondelete='CASCADE'), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=True)  # 'success' | 'error'
    records_synced = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tenant_id = Column(UUID(as_uuid=True), nullable=False)  # References tenants.id
    property_id = Column(UUID(as_uuid=True), nullable=False)  # References properties.id
    integration_id = Column(UUID(as_uuid=True), ForeignKey('integrations.id', ondelete='CASCADE'), nullable=False)
    external_id = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)  # 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled' | 'no_show'
    guest_name = Column(String(255), nullable=False)
    guest_email = Column(String(255), nullable=True)
    guest_phone = Column(String(255), nullable=True)
    room_number = Column(String(50), nullable=True)
    room_type = Column(String(100), nullable=True)
    check_in_date = Column(DateTime(timezone=False), nullable=False)  # Date of check-in
    check_out_date = Column(DateTime(timezone=False), nullable=False)  # Date of check-out
    num_nights = Column(Integer, nullable=False)
    num_adults = Column(Integer, default=1)
    num_children = Column(Integer, default=0)
    total_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    booking_source = Column(String(100), nullable=True)
    special_requests = Column(Text, nullable=True)
    booked_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('integration_id', 'external_id', name='uq_integration_external_id'),
    )
