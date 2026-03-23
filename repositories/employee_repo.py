from sqlalchemy.orm import Session
from typing import Optional, List
from models.employee import Employee
from crud.employee import employee as crud_employee
from repositories.base import BaseRepository

class EmployeeRepository(BaseRepository):
    def __init__(self):
        super().__init__(crud_employee)

    def get_by_employee_id(self, db: Session, employee_id: str, *, tenant_id: str) -> Optional[Employee]:
        return self.crud.get_by_employee_id(db, employee_id=employee_id, tenant_id=tenant_id)

    def get_multi_filtered(
        self, 
        db: Session, 
        *, 
        tenant_id: str, 
        property_id: Optional[str] = None,
        role: Optional[str] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Employee]:
        query = db.query(Employee).filter(Employee.tenant_id == tenant_id)
        if property_id:
            query = query.filter(Employee.property_id == property_id)
        if role:
            query = query.filter(Employee.role == role)
        return query.offset(skip).limit(limit).all()

employee_repo = EmployeeRepository()
