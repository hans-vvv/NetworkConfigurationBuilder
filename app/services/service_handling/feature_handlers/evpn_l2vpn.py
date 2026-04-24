from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import selectinload

from app.models import Interface
from app.repositories import get_all_devices
from app.utils import Tree

from .base import BaseFeatureHandler


class EVPN_L2VPNFeatureHandler(BaseFeatureHandler):    
    
    def compute(self, svc_ctx: dict[str, Any]) -> dict[str, Any]:
        """
        Computes on which PE interfaces connected to L2 CEs 
        l2vpn config must be applied.         
        """

        context = Tree()

        # Read implementation data from YAML definition file    
        service_data: dict[str, Any] = svc_ctx["service_data"]       

        parameters: dict[str, Any] = service_data["parameters"]        

        # List of L2VPN service definitions
        l2vpn_cfgs: list[dict[str, Any]] = parameters["l2vpns"]        
        
        # Construct base name for resource allocation (used for idempotent allocation keys)
        service_name: str = service_data["service"]
        variant: str = service_data["variant"]
        tenant: str = service_data["tenant"]
        allocation_base = service_name + "_" + variant

        # Get affected nodes for computation
        all_devices = get_all_devices(self.session)
        sel_evpn_l2vpn_devices: dict[str, Any] = service_data["selectors"]['devices']['evpn_l2vpn']
        evpn_l2vpn_devices = self.sb.selector_engine.select(all_devices, sel_evpn_l2vpn_devices)

        if not evpn_l2vpn_devices:
            raise ValueError(
                f"EVPN VPLS selector matched 0 devices for tenant={tenant} variant={variant}"
            )
                
        # Find all interfaces which needs l2vpn attachment
        interfaces = (
            self.session.query(Interface)
            .join(Interface.device)                   
            .filter(Interface.evpn_esi.is_not(None))
            .options(selectinload(Interface.device))
            .all()
        )

        # Ensure underlay readiness before computing service
        for iface in interfaces:
            if iface.evpn_esi == "needs esi":
                raise RuntimeError("Underlay not ready to compute evpn_l2vpn service")
        
        # Group discovered interfaces per device for convenience
        ifaces_by_device: dict[str, list[Interface]] = defaultdict(list)
        for iface in interfaces:
            ifaces_by_device[iface.device.hostname].append(iface)
        
        for device in evpn_l2vpn_devices:   
           
            for l2vpn_cfg in l2vpn_cfgs:
                l2vpn_name: str = l2vpn_cfg["name"]

                # Attach access interfaces
                iface_ctx = [
                    {
                        "iface_name": iface.name,                                     
                    }
                    for iface in ifaces_by_device.get(device.hostname, [])
                ] 
                base_ctx: Tree = context[device.hostname]["evpn_l2vpn"]["variant"][variant][l2vpn_name]
                base_ctx["interfaces"] = iface_ctx
                
                mtu: int = l2vpn_cfg["mtu"]
                qos_policy_name: str = l2vpn_cfg["qos_policy_name"]

                # Reserve allocations
                vlan_pool_name: str = l2vpn_cfg["allocations"]["vlan"]["poolname"]
                rd_pool_name: str = l2vpn_cfg["allocations"]["rd"]["poolname"]
                allocations = {
                    "vlan": vlan_pool_name,
                    "rd": rd_pool_name
                }
                pool_allocations = self.sb.rpa.allocate_per_service_instance(                
                    allocation_name = allocation_base + "_" + l2vpn_name,
                    allocations=allocations,
                )
                vlan = pool_allocations["vlan"]
                rd = pool_allocations["rd"]               
                
                # Populate final context
                context[device.hostname]["evpn_l2vpn"]["variant"][variant][l2vpn_name]["s_vlan"] = vlan
                context[device.hostname]["evpn_l2vpn"]["variant"][variant][l2vpn_name]["rd"] = rd
                context[device.hostname]["evpn_l2vpn"]["variant"][variant][l2vpn_name]["qos_policy_name"] = qos_policy_name
                context[device.hostname]["evpn_l2vpn"]["variant"][variant][l2vpn_name]["mtu"] = mtu
                    
                        
        return dict(context)

    