"""
KRA Schemas - Request & Response Models

Pydantic schemas for daily and weekly KRA endpoints.
Validates input and formats output with proper field constraints.
"""

from datetime import date as dt_date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ==================== DAILY KRA SCHEMAS ====================

class DailyKRABase(BaseModel):
    """Base daily KRA schema with common fields"""

    shift_changeover_status: bool
    guest_checkin_count: int = Field(ge=0)
    guest_checkout_count: int = Field(ge=0)
    complaints_logged: int = Field(ge=0)
    room_availability_checked: bool
    maintenance_tasks: int = Field(ge=0)
    cash_deposit_amount: float = Field(ge=0.0)
    google_reviews_count: int = Field(ge=0)
    notes: Optional[str] = None


class DailyKRACreate(DailyKRABase):
    """Schema for daily KRA creation"""

    date: dt_date = Field(..., description="Date for which KRA is being submitted")

    @field_validator("date")
    @classmethod
    def validate_date_not_future(cls, v: dt_date) -> dt_date:
        """Ensure date is not in the future"""
        if v > dt_date.today():
            raise ValueError("KRA date cannot be in the future")
        return v


class DailyKRAUpdate(BaseModel):
    """Schema for daily KRA updates"""

    shift_changeover_status: Optional[bool] = None
    guest_checkin_count: Optional[int] = Field(None, ge=0)
    guest_checkout_count: Optional[int] = Field(None, ge=0)
    complaints_logged: Optional[int] = Field(None, ge=0)
    room_availability_checked: Optional[bool] = None
    maintenance_tasks: Optional[int] = Field(None, ge=0)
    cash_deposit_amount: Optional[float] = Field(None, ge=0.0)
    google_reviews_count: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = None


class DailyKRAResponse(DailyKRABase):
    """Schema for daily KRA response"""

    id: int
    tenant_id: int
    user_id: int
    date: dt_date
    is_submitted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DailyKRAListResponse(BaseModel):
    """Schema for daily KRA list response"""

    id: int
    tenant_id: int
    user_id: int
    date: dt_date
    is_submitted: bool
    guest_checkin_count: int
    guest_checkout_count: int
    complaints_logged: int
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== WEEKLY KRA SCHEMAS ====================

class WeeklyKRABase(BaseModel):
    """Base weekly KRA schema with common fields"""

    ota_images_uploaded: bool
    ota_platforms: Optional[str] = Field(
        None,
        description="Comma-separated OTA platforms (e.g., Google,Booking.com,Expedia)"
    )
    supply_stock_reviewed: bool
    supply_notes: Optional[str] = None
    notes: Optional[str] = None


class WeeklyKRACreate(WeeklyKRABase):
    """Schema for weekly KRA creation"""

    week_starting_date: dt_date = Field(..., description="Monday of the week for which KRA is submitted")
    year: int = Field(..., ge=2024, le=2099)
    week_number: int = Field(..., ge=1, le=53)

    @field_validator("week_starting_date")
    @classmethod
    def validate_week_date_not_future(cls, v: dt_date) -> dt_date:
        """Ensure week start date is not in the future"""
        if v > dt_date.today():
            raise ValueError("KRA week cannot start in the future")
        return v


class WeeklyKRAUpdate(BaseModel):
    """Schema for weekly KRA updates"""

    ota_images_uploaded: Optional[bool] = None
    ota_platforms: Optional[str] = None
    supply_stock_reviewed: Optional[bool] = None
    supply_notes: Optional[str] = None
    notes: Optional[str] = None


class WeeklyKRAResponse(WeeklyKRABase):
    """Schema for weekly KRA response"""

    id: int
    tenant_id: int
    user_id: int
    week_starting_date: dt_date
    year: int
    week_number: int
    is_submitted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WeeklyKRAListResponse(BaseModel):
    """Schema for weekly KRA list response"""

    id: int
    tenant_id: int
    user_id: int
    week_starting_date: dt_date
    week_number: int
    year: int
    is_submitted: bool
    ota_images_uploaded: bool
    supply_stock_reviewed: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== MONTHLY KRA SCHEMAS ====================

class MonthlyKRABase(BaseModel):
    """Base monthly KRA schema with common fields"""

    revenue_report_url: Optional[str] = Field(
        None,
        description="S3 URL for revenue report file"
    )
    notes: Optional[str] = None


class MonthlyKRACreate(MonthlyKRABase):
    """Schema for monthly KRA creation"""

    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    year: int = Field(..., ge=2024, le=2099, description="Year")

    @field_validator("year", "month")
    @classmethod
    def validate_month_year_not_future(cls, v, info):
        """Ensure month/year is not in the future"""
        if info.field_name == "month":
            month = v
            year = info.data.get("year")
            if year and year == dt_date.today().year and month > dt_date.today().month:
                raise ValueError("KRA month cannot be in the future")
        return v


class MonthlyKRAUpdate(BaseModel):
    """Schema for monthly KRA updates"""

    revenue_report_url: Optional[str] = None
    notes: Optional[str] = None


class MonthlyKRAResponse(MonthlyKRABase):
    """Schema for monthly KRA response"""

    id: int
    tenant_id: int
    user_id: int
    month: int
    year: int
    is_submitted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MonthlyKRAListResponse(BaseModel):
    """Schema for monthly KRA list response"""

    id: int
    tenant_id: int
    user_id: int
    month: int
    year: int
    is_submitted: bool
    revenue_report_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== QUARTERLY KRA SCHEMAS ====================

class QuarterlyKRABase(BaseModel):
    """Base quarterly KRA schema with common fields"""

    revenue_report_url: Optional[str] = Field(
        None,
        description="S3 URL for revenue report file"
    )
    notes: Optional[str] = None


class QuarterlyKRACreate(QuarterlyKRABase):
    """Schema for quarterly KRA creation"""

    quarter: int = Field(..., ge=1, le=4, description="Quarter (1-4)")
    year: int = Field(..., ge=2024, le=2099, description="Year")

    @field_validator("year", "quarter")
    @classmethod
    def validate_quarter_year_not_future(cls, v, info):
        """Ensure quarter/year is not in the future"""
        if info.field_name == "quarter":
            quarter = v
            year = info.data.get("year")
            if year:
                current_date = dt_date.today()
                current_quarter = (current_date.month - 1) // 3 + 1
                if year == current_date.year and quarter > current_quarter:
                    raise ValueError("KRA quarter cannot be in the future")
        return v


class QuarterlyKRAUpdate(BaseModel):
    """Schema for quarterly KRA updates"""

    revenue_report_url: Optional[str] = None
    notes: Optional[str] = None


class QuarterlyKRAResponse(QuarterlyKRABase):
    """Schema for quarterly KRA response"""

    id: int
    tenant_id: int
    user_id: int
    quarter: int
    year: int
    is_submitted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuarterlyKRAListResponse(BaseModel):
    """Schema for quarterly KRA list response"""

    id: int
    tenant_id: int
    user_id: int
    quarter: int
    year: int
    is_submitted: bool
    revenue_report_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== KRA ANALYTICS SCHEMAS ====================

class KRAComplianceResponse(BaseModel):
    """Response schema for compliance percentage endpoint."""

    tenant_id: int
    employee_id: Optional[int] = None
    property_id: Optional[int] = None
    start_date: dt_date
    end_date: dt_date
    total_days: int
    expected_submissions: int
    actual_submissions: int
    compliance_percentage: float


class DailyReportItem(BaseModel):
    """Daily aggregate metrics for KRA reporting."""

    report_date: dt_date
    records_count: int
    total_checkins: int
    total_checkouts: int
    total_complaints: int
    total_maintenance_tasks: int
    total_google_reviews: int
    total_cash_deposit: float


class DailyReportSummary(BaseModel):
    """Summary totals for the daily report response."""

    start_date: dt_date
    end_date: dt_date
    total_days: int
    records_count: int
    total_checkins: int
    total_checkouts: int
    total_complaints: int
    total_maintenance_tasks: int
    total_google_reviews: int
    total_cash_deposit: float


class DailyReportResponse(BaseModel):
    """Response schema for daily KRA aggregate report endpoint."""

    tenant_id: int
    employee_id: Optional[int] = None
    property_id: Optional[int] = None
    summary: DailyReportSummary
    daily: list[DailyReportItem]
