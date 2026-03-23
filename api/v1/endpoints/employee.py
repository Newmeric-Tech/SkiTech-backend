from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_current_user
from models.user import User
from repositories.employee_repo import employee_repo
from crud.employee import EmployeeCreate, EmployeeUpdate

router = APIRouter()

@router.get("/", response_model=List[Any])
def read_employees(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    property_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve employees with pagination and filtering.
    """
    employees = employee_repo.get_multi_filtered(
        db, 
        tenant_id=current_user.tenant_id,
        property_id=property_id,
        role=role,
        skip=skip,
        limit=limit
    )
    return employees

@router.post("/", response_model=Any)
def create_employee(
    *,
    db: Session = Depends(get_db),
    employee_in: EmployeeCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create new employee.
    """
    # Check if employee_id already exists for this tenant
    existing = employee_repo.get_by_employee_id(
        db, employee_id=employee_in.employee_id, tenant_id=current_user.tenant_id
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Employee ID already exists."
        )
    
    return employee_repo.create(
        db, 
        obj_in=employee_in, 
        tenant_id=current_user.tenant_id,
        property_id=current_user.property_id # Default to current user's property context
    )

@router.get("/{id}", response_model=Any)
def read_employee_by_id(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get employee by ID.
    """
    employee = employee_repo.get(db, id=id, tenant_id=current_user.tenant_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee

@router.put("/{id}", response_model=Any)
def update_employee(
    *,
    db: Session = Depends(get_db),
    id: int,
    employee_in: EmployeeUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update an employee. Also used to assign employee to property.
    """
    employee = employee_repo.get(db, id=id, tenant_id=current_user.tenant_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee_repo.update(db, db_obj=employee, obj_in=employee_in)

@router.delete("/{id}", response_model=Any)
def delete_employee(
    *,
    db: Session = Depends(get_db),
    id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete an employee.
    """
    employee = employee_repo.remove(db, id=id, tenant_id=current_user.tenant_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee
