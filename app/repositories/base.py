"""
Generic base repository implementing the Repository Pattern.

Design:
- Repository Pattern:  data-access logic is centralised here, keeping
  service classes free of SQL/ORM details (Single Responsibility).
- Dependency Inversion: services depend on this abstraction, not on
  SQLAlchemy Session objects directly.
- The generic TypeVar makes the repository reusable for any ORM model
  without code duplication (Open/Closed — extend by subclassing).
"""

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Thread-unsafe base repository that wraps a SQLAlchemy session.

    Each instance is bound to a single session; the caller controls the
    session lifecycle (create → use → close).
    """

    def __init__(self, model: Type[ModelType], db: Session) -> None:
        self._model = model
        self._db = db

    def get_by_id(self, entity_id: str) -> Optional[ModelType]:
        """Fetch a single record by primary key."""
        return (
            self._db.query(self._model)
            .filter(self._model.id == entity_id)  # type: ignore[attr-defined]
            .first()
        )

    def list_all(self) -> List[ModelType]:
        """Return all records for this model."""
        return self._db.query(self._model).all()

    def add(self, instance: ModelType) -> ModelType:
        """Persist a new instance (does not commit — caller decides)."""
        self._db.add(instance)
        return instance

    def add_all(self, instances: List[ModelType]) -> None:
        """Bulk-add multiple instances without committing."""
        self._db.add_all(instances)

    def commit(self) -> None:
        """Commit the current transaction."""
        self._db.commit()

    def refresh(self, instance: ModelType) -> ModelType:
        """Refresh an instance from the DB after a commit."""
        self._db.refresh(instance)
        return instance

    def flush(self) -> None:
        """Flush pending changes to the DB within the current transaction."""
        self._db.flush()
