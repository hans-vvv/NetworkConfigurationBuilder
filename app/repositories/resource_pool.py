from sqlalchemy.orm import Session

from app.models import ResourcePool


def get_resource_pool_by_name(session: Session, name: str) -> ResourcePool | None:
    return session.query(ResourcePool).filter(ResourcePool.name == name).first()