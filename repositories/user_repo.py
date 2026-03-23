from sqlalchemy.orm import Session
from typing import Optional
from models.user import User
from crud.user import user as crud_user
from repositories.base import BaseRepository

class UserRepository(BaseRepository):
    def __init__(self):
        super().__init__(crud_user)

    def get_by_email(self, db: Session, email: str, *, tenant_id: str) -> Optional[User]:
        return db.query(User).filter(User.email == email, User.tenant_id == tenant_id).first()

user_repo = UserRepository()
