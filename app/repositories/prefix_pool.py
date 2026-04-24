from sqlalchemy.orm import Session

from app.models import PrefixPool


def get_prefix_pool_by_name(session: Session, name: str) -> PrefixPool | None:
    return session.query(PrefixPool).filter(PrefixPool.name == name).first()
