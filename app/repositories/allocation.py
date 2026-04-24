from sqlalchemy.orm import Session

from app.models import Allocation


def get_allocation_by_name(session: Session, name: str) -> Allocation | None:
    return session.query(Allocation).filter(Allocation.name == name).first()




