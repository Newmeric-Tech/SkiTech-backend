"""
Departments, Employees, Vendors - app/api/v1/endpoints/workforce.py
"""

from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_permission
from app.core.database import get_db
from app.models.models import Department, Employee, Role, Vendor
from app.schemas.schemas import (
    DepartmentCreate, DepartmentResponse, DepartmentUpdate,
    EmployeeCreate, EmployeeResponse, EmployeeUpdate,
    VendorCreate, VendorResponse, VendorUpdate,
)

# ── Departments ──────────────────────────────────────────

dept_router = APIRouter(prefix="/departments", tags=["Departments"])


@dept_router.post("/{property_id}", response_model=DepartmentResponse, status_code=201)
async def create_department(
    property_id: UUID,
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("create_department")),
):
    dept = Department(
        tenant_id=UUID(user["tenant_id"]),
        property_id=property_id,
        **data.model_dump(),
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


@dept_router.get("/{property_id}", response_model=List[DepartmentResponse])
async def list_departments(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_department")),
):
    result = await db.execute(
        select(Department).where(
            Department.property_id == property_id,
            Department.tenant_id == UUID(user["tenant_id"]),
            Department.deleted_at == None,
        )
    )
    return result.scalars().all()


@dept_router.put("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: UUID,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("update_department")),
):
    result = await db.execute(
        select(Department).where(
            Department.id == department_id,
            Department.tenant_id == UUID(user["tenant_id"]),
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(dept, k, v)
    await db.commit()
    await db.refresh(dept)
    return dept


@dept_router.delete("/{department_id}")
async def delete_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("delete_department")),
):
    result = await db.execute(
        select(Department).where(
            Department.id == department_id,
            Department.tenant_id == UUID(user["tenant_id"]),
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    dept.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Department deleted"}


# ── Employees ────────────────────────────────────────────

emp_router = APIRouter(prefix="/employees", tags=["Employees"])


@emp_router.post("/{property_id}", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    property_id: UUID,
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_staff")),
):
    import secrets as _secrets
    emp_data = data.model_dump()

    if not emp_data.get("role_id"):
        role_result = await db.execute(select(Role).where(Role.name == "Staff"))
        staff_role = role_result.scalar_one_or_none()
        if staff_role:
            emp_data["role_id"] = staff_role.id

    if not emp_data.get("employee_code"):
        emp_data["employee_code"] = "EMP-" + _secrets.token_hex(3).upper()

    emp = Employee(
        tenant_id=UUID(user["tenant_id"]),
        property_id=property_id,
        **emp_data,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return emp


@emp_router.get("/{property_id}", response_model=List[EmployeeResponse])
async def list_employees(
    property_id: UUID,
    department_id: UUID = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_staff")),
):
    q = select(Employee).where(
        Employee.property_id == property_id,
        Employee.tenant_id == UUID(user["tenant_id"]),
        Employee.deleted_at == None,
    )
    if department_id:
        q = q.where(Employee.department_id == department_id)
    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@emp_router.get("/detail/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_staff")),
):
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == UUID(user["tenant_id"]),
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@emp_router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: UUID,
    data: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_staff")),
):
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == UUID(user["tenant_id"]),
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(emp, k, v)
    await db.commit()
    await db.refresh(emp)
    return emp


@emp_router.delete("/{employee_id}")
async def delete_employee(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("manage_staff")),
):
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == UUID(user["tenant_id"]),
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Employee deleted"}


# ── Vendors ──────────────────────────────────────────────

vendor_router = APIRouter(prefix="/vendors", tags=["Vendors"])


@vendor_router.post("/{property_id}", response_model=VendorResponse, status_code=201)
async def create_vendor(
    property_id: UUID,
    data: VendorCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("create_vendor")),
):
    vendor = Vendor(
        tenant_id=UUID(user["tenant_id"]),
        property_id=property_id,
        **data.model_dump(),
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return vendor


@vendor_router.get("/{property_id}", response_model=List[VendorResponse])
async def list_vendors(
    property_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("view_vendor")),
):
    result = await db.execute(
        select(Vendor).where(
            Vendor.property_id == property_id,
            Vendor.tenant_id == UUID(user["tenant_id"]),
            Vendor.deleted_at == None,
        )
    )
    return result.scalars().all()


@vendor_router.put("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: UUID,
    data: VendorUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("update_vendor")),
):
    result = await db.execute(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.tenant_id == UUID(user["tenant_id"]),
        )
    )
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(vendor, k, v)
    await db.commit()
    await db.refresh(vendor)
    return vendor


@vendor_router.delete("/{vendor_id}")
async def delete_vendor(
    vendor_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("delete_vendor")),
):
    result = await db.execute(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.tenant_id == UUID(user["tenant_id"]),
        )
    )
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    vendor.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Vendor deleted"}
