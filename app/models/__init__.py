"""
Models __init__ - registers all models with SQLAlchemy Base
"""

from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin
from app.models.models import (
    Role, Permission, RolePermission,
    Tenant, SubscriptionPlan, TenantSubscription,
    User, Property, OwnerDetails, Employee, Department, Vendor,
    InventoryItem, InventoryMovement, LowStockAlert,
    SOPCategory, SOPItem, SOPExecution, SOPVersion, SOPRoleVisibility,
    Room, Booking, RestaurantTable, Order, OrderItem,
    GovernanceWorkflow, WorkflowInstance,
    AuditLog,
)
from app.models.chat_models import (
    Conversation, ConversationParticipant, Message, MessageMedia, MessageDeliveryStatus,
)
from app.models.ranking_models import (
    RankingCriteriaConfig, EmployeeRankingScore, EmployeeRanking,
    RankingAuditLog, RankingInsight,
)

__all__ = [
    "Base",
    "Role", "Permission", "RolePermission",
    "Tenant", "SubscriptionPlan", "TenantSubscription",
    "User", "Property", "OwnerDetails", "Employee", "Department", "Vendor",
    "InventoryItem", "InventoryMovement", "LowStockAlert",
    "SOPCategory", "SOPItem", "SOPExecution", "SOPVersion", "SOPRoleVisibility",
    "Room", "Booking", "RestaurantTable", "Order", "OrderItem",
    "GovernanceWorkflow", "WorkflowInstance",
    "AuditLog",
    # Chat
    "Conversation", "ConversationParticipant", "Message", "MessageMedia", "MessageDeliveryStatus",
    # Ranking
    "RankingCriteriaConfig", "EmployeeRankingScore", "EmployeeRanking", "RankingAuditLog", "RankingInsight",
]
