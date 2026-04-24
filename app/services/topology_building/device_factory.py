from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Device, Interface
from app.repositories import (
    get_role_by_name,
    get_site_by_name,
)
from app.utils import require


class DeviceFactory:

    """
    Factory for creating Device instances with predefined interface configurations.
    Uses device 'recipes' to expand and assign interfaces and configure device roles and sites.
    """

    DEVICE_RECIPES = { 

        "test_model_1": {
            "blocks": [
                {"start": "0/0/0", "stop": "0/0/5", "base": "Ethernet", "role": "NNI"},
                {"start": "0/0/6", "stop": "0/0/7", "base": "Ethernet", "role": "UNI"}
            ],
            "lag_name": "Bundle-Ether",
            "os_name": "ios_xr",
        },
        "test_model_2": {
            "blocks": [
                {"start": "0/0/0", "stop": "0/0/15", "base": "Ethernet", "role": "NNI"},
                {"start": "0/1/0", "stop": "0/1/15", "base": "Ethernet", "role": "UNI"}
            ],
            "lag_name": "Bundle-Ether",
            "os_name": "ios_xr",
        },        
    }
   

    def __init__(self, *, session: Session):
        """Initialize with a database session."""
        
        self.session = session

    def build_basic_device(
        self, 
        *,
        hostname: str, 
        model_name: str,
        site_name: str,
        role_name: str,
    ) -> Device:
        """Create a Device with interfaces expanded from recipe blocks."""

        try:
            recipe = self.DEVICE_RECIPES[model_name]
        except KeyError as err:
            raise ValueError(
                f"Unknown device model '{model_name}'"
            ) from err

        site = require(get_site_by_name(self.session, site_name), f"No Site found for {site_name}")
        role = require(get_role_by_name(self.session, role_name), f"No Role found for {role_name}")

        device = Device(
            hostname=hostname,            
            model_name=model_name,
            labels={},
            site=site,
            role=role
        )
        device.labels["os_name"] = recipe["os_name"]
        device.labels["lag_name"] = recipe["lag_name"]

        # expand all ranges
        for block in recipe["blocks"]:
            interfaces = self._expand_range(
                block["start"],
                block["stop"],
                block["base"],
                block["role"],                
            )

            # add interfaces to device
            for iface in interfaces:

                device.interfaces.append(
                    Interface(
                        name=iface["name"],
                        intf_role=iface["role"],                        
                    )
                )

        self.session.add(device)
        self.session.flush()
        return device  
    
    @staticmethod
    def _expand_range(
        start: str,
        stop: str,
        base: str,
        role: str ,        
    ) -> list[dict]:
        """
        Expand interface ranges where exactly one numeric component varies.
        Works for:
        - 1/1/c1     -> 1/1/c32
        - 1/1/c1/1   -> 1/1/c32/1
        """

        # Single interface
        if start == stop:
            return [{
                "name": f"{base}{start}",
                "role": role,                
            }]

        start_parts = start.split("/")
        stop_parts = stop.split("/")

        if len(start_parts) != len(stop_parts):
            raise ValueError(f"Path length mismatch: {start} - {stop}")

        # Identify varying component
        diffs = [
            i for i, (a, b) in enumerate(zip(start_parts, stop_parts, strict=False))
            if a != b
        ]

        if len(diffs) != 1:
            raise ValueError(
                f"Exactly one path component may vary: {start} - {stop}"
            )

        diff_idx = diffs[0]

        def split_suffix(value: str) -> tuple[str, int]:
            prefix = value.rstrip("0123456789")
            suffix = value[len(prefix):]
            if not suffix.isdigit():
                raise ValueError(
                    f"Non-numeric range component: {value}"
                )
            return prefix, int(suffix)

        start_prefix, start_num = split_suffix(start_parts[diff_idx])
        stop_prefix, stop_num = split_suffix(stop_parts[diff_idx])

        if start_prefix != stop_prefix:
            raise ValueError(
                f"Mismatched range prefixes: {start} - {stop}"
            )

        interfaces: list[dict] = []

        for n in range(start_num, stop_num + 1):
            parts = start_parts.copy()
            parts[diff_idx] = f"{start_prefix}{n}"
            interfaces.append({
                "name": f"{base}{'/'.join(parts)}",
                "role": role,               
                }
            )

        return interfaces
