from sqlalchemy.orm import Session

from app.models import Site


def get_site_by_name(session: Session, name: str) -> Site | None:
    return session.query(Site).filter(Site.name == name).first()


def get_all_site_names(session: Session) -> list[str]:
    sites = session.query(Site).order_by(Site.name).all()
    return [s.name for s in sites]