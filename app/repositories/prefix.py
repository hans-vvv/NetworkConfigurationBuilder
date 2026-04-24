from sqlalchemy.orm import Session

from app.models import Prefix, PrefixPool


def get_prefixes_by_pool(session: Session, pool: PrefixPool) -> list[Prefix]:
    return (
        session.query(Prefix)
        .filter(Prefix.pool_id == pool.id)
        .order_by(Prefix.prefix)
        .all()
    )
