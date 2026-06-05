"""
All SQLAlchemy ORM Models - app/models/models.py

Merged from all 4 projects:
  - skitech-Rishiiii  : full schema (tenants, RBAC, hotel, restaurant, inventory, SOP)
  - SkiTech-Nupur     : User, Property, OwnerDetails, AuditLog
  - SciTech-amardeep  : Workforce, GovernanceWorkflow, WorkflowInstance
  - Project-ansh      : basic auth/property scaffold
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, DECIMAL, Float, ForeignKey,
    Index, Integer, String, Text, TIMESTAMP, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


# ===========================================================
# RBAC
# ===========================================================

class Role(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "roles"

    name = Column(String(50), unique=True, nullable=False)
    role_level = Column(Integer, nullable=False)
    description = Column(Text)

    permissions = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )
    users = relationship("User", back_populates="role_obj")


class Permission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "permissions"

    resource = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(Text)

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_resource_action"),
    )

    roles = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "role_permissions"

    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("idx_role_permissions_permission", "permission_id"),
    )

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")


# ===========================================================
# TENANTS & SUBSCRIPTIONS
# ===========================================================

class SubscriptionPlan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "subscription_plans"

    name = Column(String(100), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    max_properties = Column(Integer)
    max_users = Column(Integer)
    features = Column(JSONB)
    stripe_price_id = Column(String(100), nullable=True)


class Tenant(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "tenants"

    business_name = Column(String(255), nullable=False)
    business_type = Column(String(50), nullable=False)
    owner_name = Column(String(255))
    contact_email = Column(String(255))
    contact_phone = Column(String(20))
    subscription_status = Column(String(50), nullable=False, default="active")
    is_active = Column(Boolean, nullable=False, default=True)
    stripe_customer_id = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("business_type IN ('hotel','restaurant','other')", name="check_business_type"),
        CheckConstraint("subscription_status IN ('active','suspended','expired')", name="check_subscription_status"),
    )

    subscriptions = relationship(
        "TenantSubscription", back_populates="tenant", cascade="all, delete-orphan"
    )
    properties = relationship("Property", back_populates="tenant")


class TenantSubscription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tenant_subscriptions"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    status = Column(String(50), nullable=False)
    stripe_subscription_id = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date > start_date", name="check_subscription_dates"),
    )

    tenant = relationship("Tenant", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan")


# ===========================================================
# USERS
# ===========================================================

class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone_number = Column(String(20))

    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    last_login = Column(DateTime)
    otp_code = Column(String(6), nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)

    role_obj = relationship("Role", back_populates="users")
    tenant = relationship("Tenant")
    property = relationship("Property", back_populates="users")


# ===========================================================
# PROPERTIES & OWNER DETAILS
# ===========================================================

class Property(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "properties"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100))
    postal_code = Column(String(20))

    # Extended fields (from SkiTech-Nupur)
    franchise_type = Column(String(50), default="owner-operated")
    num_rooms = Column(Integer)
    room_number_start = Column(Integer, default=101, nullable=True)
    has_restaurant = Column(Boolean, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    image_urls = Column(JSONB, nullable=True, default=list)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_property_name"),
        Index("idx_properties_tenant_id", "tenant_id"),
    )

    tenant = relationship("Tenant", back_populates="properties")
    users = relationship("User", back_populates="property")
    employees = relationship("Employee", back_populates="property")
    departments = relationship("Department", back_populates="property", cascade="all, delete-orphan")
    owner_details = relationship("OwnerDetails", back_populates="property", cascade="all, delete-orphan")
    vendors = relationship("Vendor", back_populates="property", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="property")
    sop_items = relationship("SOPItem", back_populates="property")


class OwnerDetails(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "owner_details"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)

    owner_name = Column(String(255), nullable=False)
    phone = Column(String(20))
    email = Column(String(255))
    address = Column(Text)
    ownership_type = Column(String(50))  # sole-owner / partnership / company
    id_proof = Column(String(255))

    __table_args__ = (
        Index("idx_owner_tenant_id", "tenant_id"),
        Index("idx_owner_property_id", "property_id"),
    )

    property = relationship("Property", back_populates="owner_details")


# ===========================================================
# EMPLOYEES
# ===========================================================

class Employee(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "employees"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)

    employee_code = Column(String(50))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255))
    phone = Column(String(20))
    position = Column(String(100))
    is_active = Column(Boolean, nullable=False, default=True)
    start_date = Column(DateTime)
    end_date = Column(DateTime)

    __table_args__ = (
        Index("idx_employees_tenant_id", "tenant_id"),
        Index("idx_employees_property_id", "property_id"),
    )

    property = relationship("Property", back_populates="employees")
    department = relationship("Department", back_populates="employees")

    # Scheduling back-refs
    availability      = relationship("EmployeeAvailability", back_populates="employee", foreign_keys="EmployeeAvailability.employee_id", cascade="all, delete-orphan")
    schedules         = relationship("WeeklySchedule",       back_populates="employee", foreign_keys="WeeklySchedule.employee_id",       cascade="all, delete-orphan")
    shift_assignments = relationship("ShiftAssignment",      back_populates="employee", foreign_keys="ShiftAssignment.employee_id",      cascade="all, delete-orphan")
    skills            = relationship("EmployeeSkill",        back_populates="employee", foreign_keys="EmployeeSkill.employee_id",        cascade="all, delete-orphan")


# ===========================================================
# DEPARTMENTS
# ===========================================================

class Department(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "departments"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_departments_tenant_id", "tenant_id"),
        Index("idx_departments_property_id", "property_id"),
        Index("idx_departments_tenant_property", "tenant_id", "property_id"),
    )

    property = relationship("Property", back_populates="departments")
    employees = relationship("Employee", back_populates="department")


# ===========================================================
# VENDORS
# ===========================================================

class Vendor(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "vendors"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    contact_person = Column(String(255))
    phone = Column(String(20))
    email = Column(String(255))
    address = Column(Text)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_vendors_tenant_id", "tenant_id"),
        Index("idx_vendors_property_id", "property_id"),
    )

    property = relationship("Property", back_populates="vendors")


# ===========================================================
# INVENTORY
# ===========================================================

class InventoryItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "inventory_items"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)

    item_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    unit = Column(String(50))
    reorder_level = Column(Integer)

    __table_args__ = (
        Index("idx_inventory_items_property_id", "property_id"),
        Index("idx_inventory_items_tenant_id", "tenant_id"),
        Index("idx_inventory_items_department_id", "department_id"),
    )

    property = relationship("Property", back_populates="inventory_items")
    movements = relationship("InventoryMovement", back_populates="item", cascade="all, delete-orphan")
    low_stock_alerts = relationship("LowStockAlert", cascade="all, delete-orphan")


class InventoryMovement(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "inventory_movements"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=False)

    movement_type = Column(String(10), nullable=False)  # IN / OUT / ADJUST
    quantity = Column(Integer, nullable=False)
    notes = Column(Text)
    reason = Column(Text)
    movement_date = Column(TIMESTAMP, server_default=func.now())

    performed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("movement_type IN ('IN','OUT','ADJUST')", name="check_movement_type"),
    )

    item = relationship("InventoryItem", back_populates="movements")


class LowStockAlert(Base, UUIDMixin):
    __tablename__ = "low_stock_alerts"

    item_id = Column(UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"))

    current_qty = Column(Integer)
    threshold_qty = Column(Integer)
    triggered_at = Column(TIMESTAMP, server_default=func.now())
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(TIMESTAMP)

    inventory_item = relationship("InventoryItem")


# ===========================================================
# SOP (Standard Operating Procedures)
# ===========================================================

class SOPCategory(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sop_categories"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text)

    __table_args__ = (
        Index("idx_sop_category_tenant", "tenant_id"),
        Index("idx_sop_category_property", "property_id"),
    )

    items = relationship("SOPItem", back_populates="category")


class SOPItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sop_items"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("sop_categories.id"), nullable=False)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    assigned_employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    title = Column(String(255), nullable=False)
    description = Column(Text)
    priority = Column(String(50), nullable=False, default="medium")  # low / medium / high
    status = Column(String(50), nullable=False, default="pending")   # pending / in_progress / completed
    due_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("priority IN ('low','medium','high')", name="check_sop_priority"),
        CheckConstraint("status IN ('pending','in_progress','completed')", name="check_sop_status"),
        Index("idx_sop_category", "category_id"),
        Index("idx_sop_status", "status"),
        Index("idx_sop_employee", "assigned_employee_id"),
        Index("idx_sop_user", "assigned_user_id"),
        Index("idx_sop_department_id", "department_id"),
    )

    category = relationship("SOPCategory", back_populates="items")
    property = relationship("Property", back_populates="sop_items")
    versions = relationship("SOPVersion", back_populates="sop_item", cascade="all, delete-orphan")
    role_visibility = relationship("SOPRoleVisibility", back_populates="sop_item", cascade="all, delete-orphan")


class SOPExecution(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sop_executions"

    sop_id = Column(UUID(as_uuid=True), ForeignKey("sop_items.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # status: pending | proof_submitted | approved | rejected
    status = Column(String(50), nullable=False, default="pending")
    completed_at = Column(DateTime, nullable=True)

    # Proof of work fields
    proof_image = Column(Text, nullable=True)       # base64 image data
    proof_submitted_at = Column(DateTime, nullable=True)
    proof_location_lat = Column(Float, nullable=True)
    proof_location_lng = Column(Float, nullable=True)
    proof_location_name = Column(String(255), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_sop_exec_user", "user_id"),
        Index("idx_sop_exec_sop", "sop_id"),
        Index("idx_sop_exec_status", "status"),
    )


class SOPVersion(Base, UUIDMixin):
    __tablename__ = "sop_versions"

    sop_item_id = Column(UUID(as_uuid=True), ForeignKey("sop_items.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)

    version_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_sop_versions_sop_item_id", "sop_item_id"),
        Index("idx_sop_versions_tenant_property", "tenant_id", "property_id"),
    )

    sop_item = relationship("SOPItem", back_populates="versions")


class SOPRoleVisibility(Base, UUIDMixin):
    __tablename__ = "sop_role_visibility"

    sop_item_id = Column(UUID(as_uuid=True), ForeignKey("sop_items.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    can_view = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_sop_role_visibility_role_id", "role_id"),
        Index("idx_sop_role_visibility_sop_id", "sop_item_id"),
    )

    sop_item = relationship("SOPItem", back_populates="role_visibility")
    role = relationship("Role")


# ===========================================================
# HOTEL (Rooms & Bookings)
# ===========================================================

class Room(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "rooms"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)

    room_number = Column(String(50), nullable=False)
    room_type = Column(String(100))
    price_per_night = Column(DECIMAL(10, 2))
    status = Column(String(50), nullable=False, default="available")

    __table_args__ = (
        UniqueConstraint("property_id", "room_number", name="uq_room_number"),
        CheckConstraint("status IN ('available','occupied','maintenance')", name="check_room_status"),
    )

    bookings = relationship("Booking", back_populates="room")


class Booking(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "bookings"

    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )

    property_id = Column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False
    )

    room_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rooms.id", ondelete="RESTRICT"),
        nullable=False
    )

    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    customer_name = Column(String(255))
    customer_phone = Column(String(20))

    check_in = Column(DateTime, nullable=False)
    check_out = Column(DateTime, nullable=False)

    total_amount = Column(DECIMAL(10, 2))

    status = Column(
        String(50),
        nullable=False,
        default="booked"
    )

    __table_args__ = (
        CheckConstraint(
            "check_out > check_in",
            name="check_booking_dates"
        ),

        CheckConstraint(
            "status IN ('booked','checked_in','completed','cancelled')",
            name="check_booking_status"
        ),
    )

    room = relationship(
        "Room",
        back_populates="bookings"
    )


# ===========================================================
# RESTAURANT (Tables & Orders)
# ===========================================================

class RestaurantTable(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "restaurant_tables"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)

    table_number = Column(String(50), nullable=False)
    capacity = Column(Integer)
    status = Column(String(50), nullable=False, default="available")

    __table_args__ = (
        UniqueConstraint("property_id", "table_number", name="uq_table_number"),
        CheckConstraint("capacity > 0", name="check_table_capacity"),
        CheckConstraint("status IN ('available','occupied')", name="check_table_status"),
    )

    orders = relationship("Order", back_populates="table")


class Order(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "orders"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    table_id = Column(UUID(as_uuid=True), ForeignKey("restaurant_tables.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    order_status = Column(String(50), nullable=False, default="pending")
    total_amount = Column(DECIMAL(10, 2))

    __table_args__ = (
        CheckConstraint(
            "order_status IN ('pending','preparing','served','completed','cancelled')",
            name="check_order_status"
        ),
    )

    table = relationship("RestaurantTable", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "order_items"

    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)

    item_name = Column(String(255))
    quantity = Column(Integer)
    price = Column(DECIMAL(10, 2))

    order = relationship("Order", back_populates="items")


# ===========================================================
# GOVERNANCE (Approval Workflows)
# ===========================================================

class GovernanceWorkflow(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "governance_workflows"

    name = Column(String(255), nullable=False, unique=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)


class WorkflowInstance(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "workflow_instances"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("governance_workflows.id"), nullable=False, index=True)
    request_type = Column(String(100), nullable=False, index=True)
    request_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    description = Column(Text)
    requested_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    current_approver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String(50), default="pending", nullable=False, index=True)
    current_step = Column(Integer, default=0, nullable=False)
    rejection_reason = Column(Text)


# ===========================================================
# AUDIT LOG
# ===========================================================

class DemoRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "demo_requests"

    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    company = Column(String(255))
    phone = Column(String(50))
    portfolio_size = Column(String(100))
    role = Column(String(100))
    message = Column(Text)
    status = Column(String(50), default="pending", index=True)  # pending / contacted / completed


class AuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    user_email = Column(String(255))

    action = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(String(255), nullable=True, index=True)

    old_values = Column(JSONB)
    new_values = Column(JSONB)
    details = Column(Text)

    property_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    ip_address = Column(INET)
    user_agent = Column(String(500))

    severity = Column(String(20), default="low")  # low / medium / high / critical
    status = Column(String(50), default="success")
    error_message = Column(Text)


# ===========================================================
# EMPLOYEE SCHEDULING  (migration 002_add_scheduling_tables)
# ===========================================================

class EmployeeAvailability(Base, UUIDMixin):
    __tablename__ = "employee_availability"

    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id",    ondelete="CASCADE"), nullable=False, index=True)
    property_id  = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id  = Column(UUID(as_uuid=True), ForeignKey("employees.id",  ondelete="CASCADE"), nullable=False, index=True)
    availability_date = Column(DateTime, nullable=False, index=True)
    status       = Column(String(50), nullable=False)   # available / unavailable / partial
    reason       = Column(String(255), nullable=True)
    notes        = Column(Text, nullable=True)
    created_at   = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at   = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "availability_date", name="uq_employee_availability_date"),
    )

    employee = relationship("Employee", back_populates="availability", foreign_keys=[employee_id])


class WeeklySchedule(Base, UUIDMixin):
    __tablename__ = "weekly_schedules"

    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id",     ondelete="CASCADE"), nullable=False, index=True)
    property_id     = Column(UUID(as_uuid=True), ForeignKey("properties.id",  ondelete="CASCADE"), nullable=False, index=True)
    employee_id     = Column(UUID(as_uuid=True), ForeignKey("employees.id",   ondelete="CASCADE"), nullable=False, index=True)
    week_start_date = Column(DateTime, nullable=False, index=True)
    week_end_date   = Column(DateTime, nullable=False)
    department_id   = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    status          = Column(String(50), nullable=False, default="draft", index=True)
    assigned_by     = Column(UUID(as_uuid=True), ForeignKey("users.id",       ondelete="SET NULL"), nullable=True)
    assigned_at     = Column(DateTime, nullable=True)
    published_at    = Column(DateTime, nullable=True)
    created_at      = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at      = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("employee_id", "week_start_date", name="uq_employee_weekly_schedule"),
    )

    employee        = relationship("Employee", back_populates="schedules",  foreign_keys=[employee_id])
    shift_assignments = relationship("ShiftAssignment", back_populates="schedule", cascade="all, delete-orphan")


class ShiftAssignment(Base, UUIDMixin):
    __tablename__ = "shift_assignments"

    tenant_id        = Column(UUID(as_uuid=True), ForeignKey("tenants.id",         ondelete="CASCADE"), nullable=False)
    property_id      = Column(UUID(as_uuid=True), ForeignKey("properties.id",      ondelete="CASCADE"), nullable=False)
    schedule_id      = Column(UUID(as_uuid=True), ForeignKey("weekly_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id      = Column(UUID(as_uuid=True), ForeignKey("employees.id",        ondelete="CASCADE"), nullable=False, index=True)
    shift_date       = Column(DateTime, nullable=False, index=True)
    shift_start_time = Column(String(5), nullable=False)
    shift_end_time   = Column(String(5), nullable=False)
    shift_type       = Column(String(50), nullable=True)
    status           = Column(String(50), nullable=False, default="scheduled", index=True)
    created_at       = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at       = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    schedule             = relationship("WeeklySchedule", back_populates="shift_assignments")
    employee             = relationship("Employee", back_populates="shift_assignments", foreign_keys=[employee_id])
    replacement_requests = relationship("ReplacementRequest", back_populates="shift_assignment", cascade="all, delete-orphan")


class ReplacementRequest(Base, UUIDMixin):
    __tablename__ = "replacement_requests"

    tenant_id               = Column(UUID(as_uuid=True), ForeignKey("tenants.id",          ondelete="CASCADE"),  nullable=False)
    property_id             = Column(UUID(as_uuid=True), ForeignKey("properties.id",       ondelete="CASCADE"),  nullable=False)
    shift_assignment_id     = Column(UUID(as_uuid=True), ForeignKey("shift_assignments.id", ondelete="CASCADE"), nullable=False)
    original_employee_id    = Column(UUID(as_uuid=True), ForeignKey("employees.id",        ondelete="CASCADE"),  nullable=False, index=True)
    replacement_employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id",        ondelete="SET NULL"), nullable=True,  index=True)
    request_date            = Column(DateTime, nullable=False)
    shift_date              = Column(DateTime, nullable=False, index=True)
    shift_start_time        = Column(String(5), nullable=False)
    shift_end_time          = Column(String(5), nullable=False)
    reason                  = Column(String(255), nullable=True)
    priority                = Column(String(50), nullable=False, default="normal", index=True)
    request_type            = Column(String(50), nullable=False)
    status                  = Column(String(50), nullable=False, default="pending", index=True)
    ai_recommended          = Column(Boolean, nullable=False, default=False)
    created_by              = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)
    responded_by            = Column(UUID(as_uuid=True), ForeignKey("employees.id",  ondelete="SET NULL"), nullable=True)
    responded_at            = Column(DateTime, nullable=True)
    response_reason         = Column(Text, nullable=True)
    created_at              = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at              = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    shift_assignment     = relationship("ShiftAssignment", back_populates="replacement_requests")
    original_employee    = relationship("Employee", foreign_keys=[original_employee_id])
    replacement_employee = relationship("Employee", foreign_keys=[replacement_employee_id])
    responses            = relationship("ShiftResponse", back_populates="replacement_request", cascade="all, delete-orphan")


class ShiftResponse(Base, UUIDMixin):
    __tablename__ = "shift_responses"

    tenant_id              = Column(UUID(as_uuid=True), ForeignKey("tenants.id",             ondelete="CASCADE"), nullable=False)
    property_id            = Column(UUID(as_uuid=True), ForeignKey("properties.id",          ondelete="CASCADE"), nullable=False)
    replacement_request_id = Column(UUID(as_uuid=True), ForeignKey("replacement_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id            = Column(UUID(as_uuid=True), ForeignKey("employees.id",           ondelete="CASCADE"), nullable=False, index=True)
    response_type          = Column(String(50), nullable=False)   # accept / decline
    reason                 = Column(Text, nullable=True)
    responded_at           = Column(DateTime, nullable=False, server_default=func.now())
    created_at             = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("replacement_request_id", "employee_id", name="uq_shift_response"),
    )

    replacement_request = relationship("ReplacementRequest", back_populates="responses")
    employee            = relationship("Employee", foreign_keys=[employee_id])


class EmployeeSkill(Base, UUIDMixin):
    __tablename__ = "employee_skills"

    tenant_id           = Column(UUID(as_uuid=True), ForeignKey("tenants.id",   ondelete="CASCADE"), nullable=False)
    employee_id         = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_name          = Column(String(100), nullable=False, index=True)
    proficiency_level   = Column(String(50), nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    verified            = Column(Boolean, nullable=False, default=False)
    created_at          = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at          = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="skills", foreign_keys=[employee_id])


# ===========================================================
# ERROR & COMPLAINT LOG  (migration 003_add_complaint_tables)
# ===========================================================

class Complaint(Base, UUIDMixin):
    __tablename__ = "complaints"

    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id",    ondelete="CASCADE"),  nullable=False, index=True)
    property_id  = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"),  nullable=False, index=True)
    created_by   = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True,  index=True)
    assigned_to  = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True,  index=True)
    assigned_by  = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)
    resolved_by  = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)

    title            = Column(String(255), nullable=False)
    description      = Column(Text, nullable=False)
    category         = Column(String(100), nullable=False, index=True)
    complaint_type   = Column(String(50), nullable=False, index=True)
    priority         = Column(String(20), nullable=False, default="medium", index=True)
    status           = Column(String(50), nullable=False, default="open",   index=True)

    room_number      = Column(String(50), nullable=True)
    location         = Column(String(255), nullable=True)

    assigned_at      = Column(DateTime, nullable=True)
    resolved_at      = Column(DateTime, nullable=True, index=True)
    resolution_notes = Column(Text, nullable=True)

    attachment_count = Column(Integer, nullable=False, default=0)
    comment_count    = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    deleted_at = Column(DateTime, nullable=True)

    creator     = relationship("User", foreign_keys=[created_by])
    assignee    = relationship("User", foreign_keys=[assigned_to])
    assigner    = relationship("User", foreign_keys=[assigned_by])
    resolver    = relationship("User", foreign_keys=[resolved_by])
    comments    = relationship("ComplaintComment",    back_populates="complaint", cascade="all, delete-orphan")
    assignments = relationship("ComplaintAssignment", back_populates="complaint", cascade="all, delete-orphan")
    attachments = relationship("ComplaintAttachment", back_populates="complaint", cascade="all, delete-orphan")


class ComplaintComment(Base, UUIDMixin):
    __tablename__ = "complaint_comments"

    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id",    ondelete="CASCADE"),  nullable=False)
    complaint_id = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"),  nullable=False, index=True)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True,  index=True)

    comment          = Column(Text, nullable=False)
    is_internal      = Column(Boolean, nullable=False, default=False)
    attachment_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    complaint   = relationship("Complaint", back_populates="comments")
    user        = relationship("User", foreign_keys=[user_id])
    attachments = relationship("ComplaintCommentAttachment", back_populates="comment", cascade="all, delete-orphan")


class ComplaintAssignment(Base, UUIDMixin):
    __tablename__ = "complaint_assignments"

    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id",    ondelete="CASCADE"),  nullable=False)
    complaint_id = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"),  nullable=False, index=True)
    assigned_to  = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="CASCADE"),  nullable=False, index=True)
    assigned_by  = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)

    assigned_at  = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    completed_at = Column(DateTime, nullable=True)
    notes        = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("complaint_id", "assigned_to", name="uq_complaint_assignment"),
    )

    complaint = relationship("Complaint", back_populates="assignments")
    assignee  = relationship("User", foreign_keys=[assigned_to])
    assigner  = relationship("User", foreign_keys=[assigned_by])


class ComplaintAttachment(Base, UUIDMixin):
    __tablename__ = "complaint_attachments"

    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("tenants.id",    ondelete="CASCADE"),  nullable=False)
    complaint_id = Column(UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"),  nullable=False, index=True)
    uploaded_by  = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True,  index=True)

    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String(50), nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    complaint = relationship("Complaint", back_populates="attachments")
    uploader  = relationship("User", foreign_keys=[uploaded_by])


class ComplaintCommentAttachment(Base, UUIDMixin):
    __tablename__ = "complaint_comment_attachments"

    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id",          ondelete="CASCADE"),  nullable=False)
    comment_id  = Column(UUID(as_uuid=True), ForeignKey("complaint_comments.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id",             ondelete="SET NULL"), nullable=True,  index=True)

    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String(50), nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    comment  = relationship("ComplaintComment", back_populates="attachments")
    uploader = relationship("User", foreign_keys=[uploaded_by])


# ===========================================================
# DOCUMENT MANAGEMENT SYSTEM  (migration 004_add_document_management_tables)
# ===========================================================

class Document(Base, UUIDMixin):
    __tablename__ = "documents"

    tenant_id                    = Column(UUID(as_uuid=True), ForeignKey("tenants.id",    ondelete="CASCADE"),  nullable=False, index=True)
    property_id                  = Column(UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"),  nullable=True,  index=True)
    uploaded_by                  = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True,  index=True)
    owner_id                     = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)
    assigned_compliance_reviewer = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)
    deleted_by                   = Column(UUID(as_uuid=True), ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)

    title          = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    category       = Column(String(100), nullable=False, index=True)
    department     = Column(String(100), nullable=True)
    file_name      = Column(String(500), nullable=False)
    file_path      = Column(String(1000), nullable=False)
    file_size      = Column(Integer, nullable=True)
    file_type      = Column(String(50), nullable=True)
    file_extension = Column(String(20), nullable=True)
    tags           = Column(String(500), nullable=True)

    access_scope        = Column(String(50),  nullable=False, default="organization_wide", index=True)
    status              = Column(String(50),  nullable=False, default="pending_review", index=True)
    approval_status     = Column(String(50),  nullable=False, default="pending")
    is_confidential     = Column(Boolean,     nullable=False, default=False)
    retention_period    = Column(Integer,     nullable=True)
    expiry_date         = Column(DateTime,    nullable=True)
    requires_signature  = Column(Boolean,     nullable=False, default=False)

    created_at    = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at    = Column(DateTime, nullable=True)
    last_modified = Column(DateTime, nullable=True)
    deleted_at    = Column(DateTime, nullable=True)

    uploader   = relationship("User", foreign_keys=[uploaded_by])
    owner      = relationship("User", foreign_keys=[owner_id])
    reviewer   = relationship("User", foreign_keys=[assigned_compliance_reviewer])
    versions   = relationship("DocumentVersion",     back_populates="document", cascade="all, delete-orphan")
    reviews    = relationship("DocumentReview",      back_populates="document", cascade="all, delete-orphan")
    approvals  = relationship("DocumentApproval",    back_populates="document", cascade="all, delete-orphan")
    shares     = relationship("DocumentShare",       back_populates="document", cascade="all, delete-orphan")
    signatures = relationship("DocumentSignature",   back_populates="document", cascade="all, delete-orphan")
    activity_logs = relationship("DocumentActivityLog", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base, UUIDMixin):
    __tablename__ = "document_versions"

    document_id        = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),  nullable=False, index=True)
    tenant_id          = Column(UUID(as_uuid=True), ForeignKey("tenants.id",   ondelete="CASCADE"),  nullable=False)
    uploaded_by        = Column(UUID(as_uuid=True), ForeignKey("users.id",     ondelete="SET NULL"), nullable=True)
    version_number     = Column(Integer, nullable=False)
    file_path          = Column(String(1000), nullable=False)
    file_size          = Column(Integer, nullable=True)
    change_description = Column(Text, nullable=True)
    created_at         = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at         = Column(DateTime, nullable=True)

    document  = relationship("Document",  back_populates="versions")
    uploader  = relationship("User",      foreign_keys=[uploaded_by])


class DocumentReview(Base, UUIDMixin):
    __tablename__ = "document_reviews"

    document_id              = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),  nullable=False, index=True)
    tenant_id                = Column(UUID(as_uuid=True), ForeignKey("tenants.id",   ondelete="CASCADE"),  nullable=False)
    reviewer_id              = Column(UUID(as_uuid=True), ForeignKey("users.id",     ondelete="SET NULL"), nullable=True,  index=True)
    reviewer_role            = Column(String(100), nullable=True)
    review_status            = Column(String(50),  nullable=False, default="pending", index=True)
    review_priority          = Column(String(50),  nullable=False, default="medium")
    comments                 = Column(Text, nullable=True)
    rejection_reason         = Column(Text, nullable=True)
    assigned_at              = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    review_started_at        = Column(DateTime, nullable=True)
    completed_at             = Column(DateTime, nullable=True)
    requires_additional_info = Column(Boolean, nullable=False, default=False)
    additional_info_request  = Column(Text, nullable=True)
    created_at               = Column(DateTime, nullable=False, server_default=func.now())
    updated_at               = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="reviews")
    reviewer = relationship("User",     foreign_keys=[reviewer_id])


class DocumentApproval(Base, UUIDMixin):
    __tablename__ = "document_approvals"

    document_id     = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),  nullable=False, index=True)
    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id",   ondelete="CASCADE"),  nullable=False)
    approver_id     = Column(UUID(as_uuid=True), ForeignKey("users.id",     ondelete="SET NULL"), nullable=True,  index=True)
    approver_role   = Column(String(100), nullable=True)
    approval_status = Column(String(50),  nullable=False, default="pending", index=True)
    approval_reason = Column(Text, nullable=True)
    conditions      = Column(JSONB, nullable=True)
    assigned_at     = Column(DateTime, nullable=False, server_default=func.now())
    decided_at      = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, nullable=False, server_default=func.now())
    updated_at      = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="approvals")
    approver = relationship("User",     foreign_keys=[approver_id])


class DocumentShare(Base, UUIDMixin):
    __tablename__ = "document_shares"

    document_id              = Column(UUID(as_uuid=True), ForeignKey("documents.id",    ondelete="CASCADE"),  nullable=False, index=True)
    tenant_id                = Column(UUID(as_uuid=True), ForeignKey("tenants.id",      ondelete="CASCADE"),  nullable=False)
    shared_with_user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id",        ondelete="CASCADE"),  nullable=True,  index=True)
    shared_with_department_id= Column(UUID(as_uuid=True), ForeignKey("departments.id",  ondelete="CASCADE"),  nullable=True,  index=True)
    shared_by                = Column(UUID(as_uuid=True), ForeignKey("users.id",        ondelete="SET NULL"), nullable=True)
    permission_level         = Column(String(50),  nullable=False, default="view")
    shared_at                = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    expires_at               = Column(DateTime, nullable=True)
    is_active                = Column(Boolean,  nullable=False, default=True)
    created_at               = Column(DateTime, nullable=False, server_default=func.now())
    updated_at               = Column(DateTime, nullable=True)

    document   = relationship("Document",    back_populates="shares")
    shared_user= relationship("User",        foreign_keys=[shared_with_user_id])
    sharer     = relationship("User",        foreign_keys=[shared_by])


class DocumentSignature(Base, UUIDMixin):
    __tablename__ = "document_signatures"

    document_id                 = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),  nullable=False, index=True)
    tenant_id                   = Column(UUID(as_uuid=True), ForeignKey("tenants.id",   ondelete="CASCADE"),  nullable=False)
    signer_id                   = Column(UUID(as_uuid=True), ForeignKey("users.id",     ondelete="SET NULL"), nullable=True,  index=True)
    signer_name                 = Column(String(255), nullable=False)
    signer_email                = Column(String(255), nullable=False)
    signer_role                 = Column(String(100), nullable=True)
    signature_status            = Column(String(50),  nullable=False, default="pending", index=True)
    signature_image             = Column(Text, nullable=True)
    signature_request_sent_at   = Column(DateTime, nullable=True)
    signed_at                   = Column(DateTime, nullable=True)
    decline_reason              = Column(Text, nullable=True)
    created_at                  = Column(DateTime, nullable=False, server_default=func.now())
    updated_at                  = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="signatures")
    signer   = relationship("User",     foreign_keys=[signer_id])


class DocumentActivityLog(Base, UUIDMixin):
    __tablename__ = "document_activity_logs"

    document_id       = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),  nullable=False, index=True)
    tenant_id         = Column(UUID(as_uuid=True), ForeignKey("tenants.id",   ondelete="CASCADE"),  nullable=False)
    performed_by      = Column(UUID(as_uuid=True), ForeignKey("users.id",     ondelete="SET NULL"), nullable=True,  index=True)
    action            = Column(String(100), nullable=False, index=True)
    activity_type     = Column(String(50),  nullable=False)
    performed_by_name = Column(String(255), nullable=True)
    performed_by_role = Column(String(100), nullable=True)
    details           = Column(JSONB, nullable=True)
    description       = Column(Text, nullable=True)
    ip_address        = Column(String(50),  nullable=True)
    user_agent        = Column(String(500), nullable=True)
    created_at        = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at        = Column(DateTime, nullable=True)

    document  = relationship("Document", back_populates="activity_logs")
    performer = relationship("User",     foreign_keys=[performed_by])


class DocumentTemplate(Base, UUIDMixin):
    __tablename__ = "document_templates"

    tenant_id        = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name             = Column(String(255), nullable=False)
    description      = Column(Text, nullable=True)
    category         = Column(String(100), nullable=False, index=True)
    template_content = Column(Text, nullable=False)
    required_fields  = Column(JSONB, nullable=True)
    usage_count      = Column(Integer, nullable=False, default=0)
    is_active        = Column(Boolean,  nullable=False, default=True)
    created_at       = Column(DateTime, nullable=False, server_default=func.now())
    updated_at       = Column(DateTime, nullable=True)
    deleted_at       = Column(DateTime, nullable=True)
    is_system_action = Column(Boolean, default=False)
