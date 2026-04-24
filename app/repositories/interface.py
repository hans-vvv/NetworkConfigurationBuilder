from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Cable, Device, Interface


def get_used_interfaces_by_device(session: Session, device: Device):

    stmt = (
        select(Interface)
        .where(
            Interface.device_id == device.id,
            Interface.in_use,
        )
        .order_by(Interface.id)
    )
    return list(session.scalars(stmt))


def get_loopback_interface(session: Session, device: Device, loop_index: int) -> Interface | None:
    name = f"Loopback{loop_index}"
    return (
        session.query(Interface)
        .filter_by(device_id=device.id, name=name)
        .first()
    )

def get_intf_by_name_by_device(
    session: Session, 
    device: Device, 
    intf_name: str,
) -> Interface | None:
    return session.query(Interface).filter(
        Interface.device_id == device.id,
        Interface.name == intf_name
    ).first()


def get_interface_names_by_device_without_cable_connected(session: Session, device: Device) -> list[str]:
    interfaces = (
        session.query(Interface)
        .filter(Interface.device_id == device.id)
        .all()
    )
    result = []
    for iface in interfaces:

        # Skip loopbacks
        if iface.name.lower().startswith("lo"):
            continue
        if "loopback" in iface.name.lower():
            continue

        # Must have no cable on either side
        if not iface.cables_as_a and not iface.cables_as_b:
            result.append(iface.name)
    return result


def get_remote_device_role_for_interface(
    session: Session,
    *,
    iface: Interface,
) -> Optional[str]:
    """
    Returns remote device role for an interface.

    Handles LAGs:
      - If iface is a LAG parent, tries its member interfaces (children)
      - If iface is a physical interface, checks it directly

    Returns None if no in-use cable adjacency is found or remote side is incomplete.
    """

    # Candidate interface IDs that may actually have the cable attached
    candidate_ifaces: list[Interface] = []

    # LAG parent: cable likely attached to members
    if iface.children:
        candidate_ifaces.extend(iface.children)
    else:
        candidate_ifaces.append(iface)

    for cand in candidate_ifaces:
        cable = (
            session.query(Cable)
            .filter(Cable.in_use)
            .filter(or_(Cable.interface_a_id == cand.id, Cable.interface_b_id == cand.id))
            .first()
        )
        if cable is None:
            continue

        remote_iface_id = (
            cable.interface_b_id if cable.interface_a_id == cand.id else cable.interface_a_id
        )

        remote_iface = (
            session.query(Interface)
            .filter(Interface.id == remote_iface_id)
            .first()
        )
        if remote_iface is None or remote_iface.device is None or remote_iface.device.role is None:
            return None

        return remote_iface.device.role.name

    return None
