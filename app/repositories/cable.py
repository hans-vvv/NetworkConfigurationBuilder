from sqlalchemy.orm import Session, aliased

from app.models import Cable, Device, Interface


def get_cables_between_devices(
    session: Session,
    device_a: Device,
    device_b: Device
) -> list[Cable]:
    """Return all cables that connect device_a and device_b, in any direction."""

    iface_a = aliased(Interface)
    iface_b = aliased(Interface)

    return (
        session.query(Cable)
        .join(iface_a, Cable.interface_a_id == iface_a.id)
        .join(iface_b, Cable.interface_b_id == iface_b.id)
        .filter(
            (
                (iface_a.device_id == device_a.id) &
                (iface_b.device_id == device_b.id)
            )
            |
            (
                (iface_a.device_id == device_b.id) &
                (iface_b.device_id == device_a.id)
            )
        )
        .all()
    )

