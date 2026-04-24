from sqlalchemy.orm import Session

from app.models import ServiceInstance


def get_service_instance_by_name(session: Session, name: str) -> ServiceInstance | None:
    return session.query(ServiceInstance).filter(ServiceInstance.svc_name == name).one_or_none()


