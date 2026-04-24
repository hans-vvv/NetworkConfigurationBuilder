from sqlalchemy.orm import Session

from app.models import Device, Role


def get_device_by_hostname(session: Session, hostname: str) -> Device | None:
    return session.query(Device).filter(Device.hostname == hostname).first()


def get_all_devices(session: Session) -> list[Device]:
    return session.query(Device).order_by(Device.id).all()


def get_all_device_names(session: Session) -> list[str]:
    devices = session.query(Device).order_by(Device.hostname).all()
    return [d.hostname for d in devices]


def get_devices_by_role(session: Session, role: Role) -> list[Device]:
    return (
        session.query(Device)
        .filter(Device.role_id == role.id)
        .order_by(Device.hostname)
        .all()
    )

def get_devices_by_role_name(session: Session, role_name: str) -> list[Device]:
    return (
        session.query(Device)
        .join(Role)
        .filter(Role.name == role_name)
        .order_by(Device.hostname)
        .all()
    )

