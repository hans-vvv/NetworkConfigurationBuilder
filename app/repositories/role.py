from sqlalchemy.orm import Session

from app.models import Role


def get_role_by_name(session: Session, name: str) -> Role | None:
    return session.query(Role).filter(Role.name == name).first()


def get_all_role_names(session: Session) -> list[str]:
    roles = session.query(Role).order_by(Role.name).all()
    return [r.name for r in roles]