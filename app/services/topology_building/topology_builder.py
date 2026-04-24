from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Cable, PrefixPool
from app.repositories import (
    get_device_by_hostname,
    get_intf_by_name_by_device,
)
from app.services.service_handling.resource_pool_allocator import ResourcePoolAllocator
from app.services.topology_building.cable_builder import CableBuilder
from app.services.topology_building.device_builder import DeviceBuilder
from app.utils import require


class TopologyBuilder:
    """
    Orchestrate topology-level link construction between existing devices.
    """    

    def __init__(
        self,
        *,
        session: Session,
        device_builder: DeviceBuilder,
        prefix_allocator: ResourcePoolAllocator,
        cable_builder: CableBuilder,
    ) -> None:
        self.session = session
        self.device_builder = device_builder
        self.prefix_allocator = prefix_allocator
        self.cable_builder = cable_builder

    def build_p2p_link(
        self,
        dev_a_name: str,
        dev_b_name: str,
        pool: PrefixPool,
        *,
        on_lag: bool,
        iface_a_name: Optional[str] = None,
        iface_b_name: Optional[str] = None,
    ) -> Cable:
        """
        Build a routed point-to-point link between two devices.

        Interface selection precedence is:

        1. caller-supplied interface names
        2. automatic free-NNI selection
        """
        dev_a = require(
            get_device_by_hostname(self.session, dev_a_name),
            f"No dB record found for device '{dev_a_name}'",
        )
        dev_b = require(
            get_device_by_hostname(self.session, dev_b_name),
            f"No dB record found for device '{dev_b_name}'",
        ) 
      
        if iface_a_name is None:
            iface_a = self.device_builder.select_free_nni(dev_a)
        else:
            iface_a = require(
                get_intf_by_name_by_device(self.session, dev_a, iface_a_name),
                f"No dB record found for interface '{iface_a_name}' on {dev_a.hostname}",
            )

        if iface_b_name is None:
            iface_b = self.device_builder.select_free_nni(dev_b)
        else:
            iface_b = require(
                get_intf_by_name_by_device(self.session, dev_b, iface_b_name),
                f"No dB record found for interface '{iface_b_name}' on {dev_b.hostname}",
            )        

        iface_a.in_use = True
        iface_b.in_use = True

        prefix = self.prefix_allocator.allocate_p2p_prefix(pool)
        ip_a, ip_b = self.prefix_allocator.allocate_ips_for_p2p(prefix)
        ip_a.in_use = True
        ip_b.in_use = True

        cable = self.cable_builder.connect(iface_a, iface_b)
        cable.in_use = True

        iface_a.description = f"Remote: {dev_b.hostname}:{iface_b.name}"
        iface_b.description = f"Remote: {dev_a.hostname}:{iface_a.name}"

        if on_lag:
            lag_a = self.device_builder.create_nni_lag(dev_a)
            self.device_builder.attach_to_lag(iface_a, lag_a)
            lag_a.in_use = True

            lag_b = self.device_builder.create_nni_lag(dev_b)
            self.device_builder.attach_to_lag(iface_b, lag_b)
            lag_b.in_use = True

            lag_a.description = f"Remote: {dev_b.hostname}:{lag_b.name}"
            lag_b.description = f"Remote: {dev_a.hostname}:{lag_a.name}"

            self.device_builder.assign_ip_address_to_interface(lag_a, ip_a)
            self.device_builder.assign_ip_address_to_interface(lag_b, ip_b)
        else:
            self.device_builder.assign_ip_address_to_interface(iface_a, ip_a)
            self.device_builder.assign_ip_address_to_interface(iface_b, ip_b)

        self.session.flush()
        return cable
    