from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.domain.file_locations import SERVICES_DEF_LOC
from app.models import ServiceDescriptor
from app.services.service_handling.service_builder import ServiceBuilder
from app.utils import require
from app.validation.service_definition import ServiceDefinitionDocument

DefKey = tuple[str, str, str]  # (service, tenant, variant)


SERVICE_DESCRIPTORS: list[ServiceDescriptor] = [
    ServiceDescriptor(
        name="isis",
        definition_schema=ServiceDefinitionDocument,        
        feature_handlers={
            "isis": "app.services.service_handling.feature_handlers.isis.ISISCoreFeatureHandler"
        },
    ),
    ServiceDescriptor(
        name="sr",
        definition_schema=ServiceDefinitionDocument,        
        feature_handlers={
            "sr": "app.services.service_handling.feature_handlers.sr.SRFeatureHandler"
        },
    ),
    ServiceDescriptor(
        name="bgp",
        definition_schema=ServiceDefinitionDocument,        
        feature_handlers={
            "bgp": "app.services.service_handling.feature_handlers.bgp.BGPFeatureHandler",
        },
    ),
    ServiceDescriptor(
        name="evpn_esi",
        definition_schema=ServiceDefinitionDocument,        
        feature_handlers={
            "evpn_esi": "app.services.service_handling.feature_handlers.evpn_esi.EVPN_ESIFeatureHandler",
        },
    ),    
    ServiceDescriptor(
        name="evpn_l2vpn",
        definition_schema=ServiceDefinitionDocument,        
        feature_handlers={
            "evpn_l2vpn": "app.services.service_handling.feature_handlers.evpn_l2vpn.EVPN_L2VPNFeatureHandler",
        },
    ),    
]


class ServiceOrchestrator:
    """
    Deterministically executes ServiceBuilder in the correct order.
    Validates all service YAML definition files.

    Model:

    - Single service file:
          Exactly one `*_def.yaml` file per (service, tenant, variant).
          Each file contains the full service specification.

    Determinism guarantees:

      - Services are executed in SERVICE_DESCRIPTORS order.
      - Tenants are processed in sorted order.
      - Variants are processed in sorted order.

    Constraints:

      - At least one definition file per discovered service/tenant pair.
      - Variant values must be unique within a (service, tenant).
    """

    def __init__(self, *, service_builder: ServiceBuilder):
        self.sb = service_builder        

    # ----------------------------
    # Public API
    # ----------------------------
    def submit(self) -> None:        

        """
        Performs validation/discovery of YAML definition files.
        Calls ServiceBuilder in deterministic order.
        """

        self._validate_yaml_service_files()

        defs_by_key = self._discover_definitions_by_key()
        
        variants_by_service_tenant: dict[tuple[str, str], list[str]] = {}
        for service, tenant, variant in defs_by_key.keys():
            variants_by_service_tenant.setdefault((service, tenant), []).append(variant)

        for key in variants_by_service_tenant:
            variants_by_service_tenant[key].sort()

        for descriptor in SERVICE_DESCRIPTORS:
            service = descriptor.name

            tenants = sorted(
                {tenant for svc, tenant, _variant in defs_by_key.keys() if svc == service}
            )
            if not tenants:
                continue

            for tenant in tenants:
                variants = require(
                    variants_by_service_tenant.get((service, tenant)),
                    f"No variants found for service={service!r}, tenant={tenant!r}",
                )

                for variant in variants:
                    def_path = defs_by_key[(service, tenant, variant)]
                    service_data = self._load_service_yaml(def_path)

                    svc_ctx = {
                        "service_data": service_data,                        
                    }

                    if descriptor.feature_handlers:
                        self.sb.compute(svc_ctx, descriptor)

    def _validate_yaml_service_files(self) -> None:
        """
        Validate all service definition YAML files.

        Rules:
        - Each definition is validated against the definition schema
          for its service type.
        - Raises on first validation error.
        """
        desc_by_service = {d.name: d for d in SERVICE_DESCRIPTORS}
        defs_by_key = self._discover_definitions_by_key()

        for (service, tenant, variant), def_path in defs_by_key.items():
            descriptor = require(
                desc_by_service.get(service),
                f"No ServiceDescriptor registered for service={service!r} "
                f"(tenant={tenant!r}, variant={variant!r})",
            )
            raw_def = self._load_service_yaml(def_path)            
            descriptor.definition_schema.model_validate(raw_def)

    # ----------------------------
    # Discovery
    # ----------------------------
    def _discover_definitions_by_key(self) -> dict[DefKey, Path]:
        """
        Discover all definition YAML files (by filename convention *_def.yaml)
        and index them by (service, tenant, variant). Enforces uniqueness.
        Deterministic: processes files in sorted filename order.
        """
        defs: dict[DefKey, Path] = {}

        for path in sorted(Path(SERVICES_DEF_LOC.location).glob("*_def.yaml"), key=lambda p: p.name):
            data = self._load_service_yaml(path)

            service = require(data.get("service"), f"Missing 'service' in definition: {path}")
            tenant = require(data.get("tenant"), f"Missing 'tenant' in definition: {path}")
            variant = require(data.get("variant"), f"Missing 'variant' in definition: {path}")

            key: DefKey = (service, tenant, variant)
            if key in defs:
                raise ValueError(
                    f"Duplicate service definition for (service, tenant, variant)={key}: "
                    f"{defs[key]} and {path}"
                )

            defs[key] = path

        return defs    

    @staticmethod
    @lru_cache(maxsize=None)
    def _load_service_yaml(loc: Path) -> dict[str, Any]:
        """Load YAML file."""
        loc = loc.resolve()
        require(loc.exists(), f"YAML file not found: {loc}")

        with loc.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return data or {}
    