from __future__ import annotations

from typing import Any

from app.repositories import get_all_devices, get_loopback_ip_from_device
from app.utils import Tree

from .base import BaseFeatureHandler


class BGPFeatureHandler(BaseFeatureHandler):
    """
    Builds iBGP peering relationships using declarative selectors.

    Supports:
      - RR / RR-client topologies
      - Full-mesh iBGP
      - Arbitrary device groups via selectors
    """

    def compute(self, svc_ctx: dict[str, Any]):
        service_data = svc_ctx["service_data"]

        bgp_cfg: dict[str, Any] = service_data["features"]["bgp"]
        variant: str = service_data["variant"]

        asn: int = bgp_cfg["asn"]        
        pg_rr: str = bgp_cfg["rr"]["rr_peer_group_name"]
        pg_rrc: str = bgp_cfg["rr"]["rrc_peer_group_name"]        
        
        context = Tree()

        all_devices = get_all_devices(self.session)
        sel_bgp_devices: dict[str, Any] = service_data["selectors"]["devices"]["bgp"]
        sel_rr_devices: dict[str, Any] = service_data["selectors"]["devices"]["route_reflectors"]

        bgp_devices = self.sb.selector_engine.select(all_devices, sel_bgp_devices)
        rr_devices = self.sb.selector_engine.select(all_devices, sel_rr_devices)

        if not bgp_devices or not rr_devices:
            raise ValueError(
                f"BGP selector matched 0 devices or RRs for tenant={service_data['tenant']}"
            )        

        # ============================================================
        # EXPLICIT ROUTE REFLECTOR TOPOLOGY
        # ============================================================
        for dev in bgp_devices:
            is_rr = dev in rr_devices

            # --------------------------------------------------------
            # RR BEHAVIOR
            # --------------------------------------------------------
            if is_rr:
                peers = []
                
                for peer in bgp_devices:
                    if peer.id == dev.id:
                        continue
                    if peer in rr_devices:
                        continue  # no RR-RR sessions here

                    # TODO: use require helper.
                    lo = get_loopback_ip_from_device(self.session, peer, 0)
                    if not lo:
                        continue      
                    
                    peers.append(
                        {
                            "neighbor_ip": lo.address.split("/")[0],
                            "remote_as": asn,
                            "peer_group": pg_rrc,
                            "neighbor_hostname": peer.hostname,
                        }
                    )
               
                context[dev.hostname]["bgp"]["variant"][variant] = {
                    "asn": asn,
                    "topology_role": "rr",
                    "peer_group": pg_rrc,
                    "neighbors": peers,
                    
                }
                
            # --------------------------------------------------------
            # CLIENT BEHAVIOR
            # --------------------------------------------------------
            else:
                peers = []
               
                for rr in rr_devices:

                    lo = get_loopback_ip_from_device(self.session, rr, 0)
                    if not lo:
                        continue

                    peers.append(
                        {
                            "neighbor_ip": lo.address.split("/")[0],
                            "remote_as": asn,
                            "peer_group": pg_rr,
                            "neighbor_hostname": rr.hostname,                            
                        }
                    )

                context[dev.hostname]["bgp"]["variant"][variant] = {
                    "asn": asn,
                    "topology_role": "client",
                    "peer_group": pg_rrc,
                    "neighbors": peers,
                } 

        return dict(context)
    