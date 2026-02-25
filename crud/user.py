from pydantic import BaseModel, EmailStr
from crud.base import CRUDBase
from models.user import User

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    username: str = None
    email: EmailStr = None
    password: str = None

class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    def create(self, db: Session, *, obj_in: UserCreate, tenant_id: str, property_id: str) -> User:
        from core.security import get_password_hash
        db_obj = User(
            username=obj_in.username,
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            tenant_id=tenant_id,
            property_id=property_id,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

user = CRUDUser(User)
