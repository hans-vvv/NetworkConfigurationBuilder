from sqlalchemy.orm import Session

from app.models import PrefixPoolType


def get_prefix_pool_type_by_name(session: Session, name: str) -> PrefixPoolType | None:
    return session.query(PrefixPoolType).filter(PrefixPoolType.name == name).first()
