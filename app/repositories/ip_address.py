from sqlalchemy.orm import Session

from app.models import Device, Interface, IPAddress, PrefixPool

from .interface import get_loopback_interface


def get_ips_for_pool(session: Session, pool: PrefixPool) -> list[IPAddress]:
    return (
        session.query(IPAddress)
        .filter(IPAddress.pool_id == pool.id)
        .order_by(IPAddress.address)
        .all()
    )

def get_ips_for_interface(session: Session, interface: Interface) -> list[IPAddress]:
    return (
        session.query(IPAddress)
        .filter(IPAddress.interface_id == interface.id)
        .order_by(IPAddress.address)
        .all()
    )

def get_loopback_ip_from_device(session: Session, device: Device, loop_index: int) -> IPAddress | None:
    """Return the loopback IPAddress for a device's Loopback{loop_index}, if present.   
    """
    iface = get_loopback_interface(session, device, loop_index)
    if not iface:       
        return None

    ips = get_ips_for_interface(session, iface)
    loop_ips = [ip for ip in ips]
    if not loop_ips:       
        return None
    
    loop_ips.sort(key=lambda ip: ip.address)    
    return loop_ips[0]
