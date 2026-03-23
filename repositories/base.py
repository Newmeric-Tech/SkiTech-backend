from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from sqlalchemy.orm import Session
from crud.base import CRUDBase, ModelType, CreateSchemaType, UpdateSchemaType

class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, crud: CRUDBase[ModelType, CreateSchemaType, UpdateSchemaType]):
        self.crud = crud

    def get(self, db: Session, id: Any, *, tenant_id: str) -> Optional[ModelType]:
        return self.crud.get(db, id, tenant_id=tenant_id)

    def get_multi(
        self, db: Session, *, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        return self.crud.get_multi(db, tenant_id=tenant_id, skip=skip, limit=limit)

    def create(
        self, db: Session, *, obj_in: CreateSchemaType, tenant_id: str, property_id: str
    ) -> ModelType:
        return self.crud.create(db, obj_in=obj_in, tenant_id=tenant_id, property_id=property_id)

    def update(
        self, db: Session, *, db_obj: ModelType, obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        return self.crud.update(db, db_obj=db_obj, obj_in=obj_in)

    def remove(self, db: Session, *, id: Any, tenant_id: str) -> Optional[ModelType]:
        return self.crud.remove(db, id=id, tenant_id=tenant_id)
