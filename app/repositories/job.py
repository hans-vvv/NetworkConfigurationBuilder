from sqlalchemy.orm import Session

from app.models import Job


def get_job_by_name(session: Session, name: str) -> Job | None:
    return session.query(Job).filter(Job.name == name).first()
