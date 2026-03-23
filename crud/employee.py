from typing import Optional
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from crud.base import CRUDBase
from models.employee import Employee

class EmployeeBase(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = True
    employee_id: Optional[str] = None

class EmployeeCreate(EmployeeBase):
    full_name: str
    email: EmailStr
    role: str
    employee_id: str

class EmployeeUpdate(EmployeeBase):
    pass

class CRUDEmployee(CRUDBase[Employee, EmployeeCreate, EmployeeUpdate]):
    def get_by_employee_id(self, db: Session, employee_id: str, *, tenant_id: str) -> Optional[Employee]:
        return db.query(Employee).filter(
            Employee.employee_id == employee_id,
            Employee.tenant_id == tenant_id
        ).first()

employee = CRUDEmployee(Employee)
