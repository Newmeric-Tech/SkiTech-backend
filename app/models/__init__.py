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
    Conversation, ConversationParticipant, Message, MessageMedia,
    MessageDeliveryStatus, TypingIndicator, ChatNotification,
)
from app.models.ranking_models import (
    RankingCriteriaConfig, EmployeeRankingScore, EmployeeRanking,
    RankingAuditLog, RankingInsight,
)
from app.models.kra import DailyKRA, WeeklyKRA, MonthlyKRA, QuarterlyKRA
from app.models.workforce_entry import WorkforceEntry

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
    "Conversation", "ConversationParticipant", "Message", "MessageMedia",
    "MessageDeliveryStatus", "TypingIndicator", "ChatNotification",
    "RankingCriteriaConfig", "EmployeeRankingScore", "EmployeeRanking",
    "RankingAuditLog", "RankingInsight",
    "DailyKRA", "WeeklyKRA", "MonthlyKRA", "QuarterlyKRA",
    "WorkforceEntry",
]
