from __future__ import annotations

from app.models.dataclass_models import DeviceSelectorView, RoleView
from app.repositories import (
    get_device_by_hostname,
    get_prefix_pool_by_name,
)
from app.services.job_handling.base import BaseActionJobHandler
from app.utils import require


class AddDeviceJobHandler(BaseActionJobHandler):
    """
    Handles the job to add a new device to the network.

    Checks for existing device to ensure idempotency, builds a new device
    using a predefined model and prefix pool, and triggers underlay recomputation.
    """

    def identity(self, step: dict) -> str:
        """Generate a unique identity string for the job step based on hostname."""
        dev = step["params"]["hostname"]        
        return f"add_device {dev}" 

    def handle(self, step: dict) -> dict:
        """
        Execute the job step to add a device.

        Returns device creation status and ID, or existing device info if already present.
        """
        params = step["params"]

        # If device already created earlier in same job → return it
        hostname = step["params"]["hostname"]

        existing = get_device_by_hostname(self.session, hostname)
        if existing:
            return {
                "device_id": existing.id,
                "status": "exists",
            }
        
        # Before creating Device object resolve loopback pool, without depending
        # of a real Device object (chicken-egg problem)
        view = DeviceSelectorView(
            hostname=params["hostname"],
            labels = {"tenant": params["tenant"]},
            role=RoleView(name=params["role"])
        )        
        loop0_pool_name = self.executor.addressing_policy_resolver.resolve_loopback0_pool(view)
        
        loop0_pool = require(
            get_prefix_pool_by_name(self.session, loop0_pool_name),
            f"PrefixPool '{loop0_pool_name}' missing"
        )
        
        # --- Build device ---
        device = self.executor.device_builder.build_device(
            hostname=params["hostname"],
            model_name=params["model_name"],
            role_name=params["role"],
            site_name=params["site"],
            loopback0_pool=loop0_pool,            
            tenant=params["tenant"],
            ring=params.get("ring")
        )
        print(f"Device {params["hostname"]} build")
       
        return {
            "device_id": device.id,
            "status": "created",
            "topology_changed": True
        }
