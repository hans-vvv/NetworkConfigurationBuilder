from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from functools import cached_property
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy.orm import Session

from app.models import ServiceInstance
from app.repositories import get_device_by_hostname
from app.services.context.device_context import DeviceContextComposer
from app.services.context.services_context import compose_services
from app.utils import db_session, deep_merge, jprint, peer_ip_on_p2p, require

TEMPLATE_MAP = {        
    "test_model_1": Path("app/services/templates/sros"),
    "test_model_2": Path("app/services/templates/sros"),    
}


class Printer:
    """
    Renders device configuration using Jinja2 templates.
   
    - device_ctx is created once per device render
    - service composition mutate the same device_ctx. This
      context is assumed to have all interfaces attached.
    """

    def __init__(self, *, session: Session):
        self.session = session
        self.dcc = DeviceContextComposer(session=session)
        self._env_cache: dict[Path, Environment] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_device(self, *, hostname: str) -> str:
        return self._render(hostname=hostname)

    def print_all(self) -> dict[str, str]:
        result: dict[str, str] = {}

        for hostname in self._collect_devices():
            result[hostname] = self.render_device(hostname=hostname)
            
        return result

    # ------------------------------------------------------------------
    # Jinja environment
    # ------------------------------------------------------------------

    def _get_env(self, template_dir: Path) -> Environment:
        env = self._env_cache.get(template_dir)
        if env is not None:
            return env

        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["peer_ip_on_p2p"] = peer_ip_on_p2p

        self._env_cache[template_dir] = env
        return env

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------
    @cached_property
    def _collect_services_computed(self) -> dict[str, Any]:
        """
        Merges information from services
        computed by feature handlers
        """
        result: dict[str, Any] = {}

        service_instances = (
            self.session.query(ServiceInstance)
            .filter(ServiceInstance.computed.is_not({}))           
        )

        for svc_inst in service_instances:            
            result = deep_merge(result, svc_inst.computed)
        
        # jprint(result["pe1.Site9"])

        return result

    def _collect_devices(self) -> list[str]:
        """
        Returns all devices with any service present
        """
        return list(self._collect_services_computed.keys())

    def _build_service_intent(
        self,
        *,
        device_ctx: dict[str, Any],
        hostname: str,
    ) -> dict[str, Any]:
        """
        Returns complete global and interface level intent for all 
        services per device  
        """
        service_intent = self._collect_services_computed.get(hostname, {})
        
        return compose_services(
            device_ctx=device_ctx,
            service_intent=service_intent,
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _select_base_template(self, *, hostname: str) -> Path:
        """
        Select appropriate J2 template based on device model name
        """
        device = require(get_device_by_hostname(self.session, hostname=hostname),
                         f"No DB row present for {hostname}")
               
        return TEMPLATE_MAP[device.model_name]

    def _build_render_ctx(self, *, hostname: str) -> dict[str, Any]:
        """
        Final render context for a device.        
        """
       
        device_ctx = self.dcc.compose(hostname=hostname)

        service_ctx = self._build_service_intent(
            device_ctx=device_ctx,
            hostname=hostname,
        )
        
        result =  {
            **device_ctx,    
            **service_ctx,            
        }
        # jprint(result)
        return result

    def _render(self, *, hostname: str) -> str:
        """
        Renders final device config        
        """
        template_dir = self._select_base_template(hostname=hostname)
        env = self._get_env(template_dir)

        template = env.get_template("base.j2")
        ctx = self._build_render_ctx(hostname=hostname)

        return template.render(**ctx)
    

if __name__ == "__main__":

    with db_session() as session:

        printer = Printer(session=session)
        # printer.render_device(hostname="pe1.Site9")
        print(printer.render_device(hostname="pe1.Site9"))

        
        