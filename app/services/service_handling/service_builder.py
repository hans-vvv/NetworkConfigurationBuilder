from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Type

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import ServiceInstance
from app.services.selectors.selector_engine import SelectorEngine
from app.services.service_handling.resource_pool_allocator import ResourcePoolAllocator
from app.utils import deep_merge

if TYPE_CHECKING:
    from .service_orchestrator import ServiceDescriptor


class ServiceBuilder:
    """
    Executes service-specific feature computation for validated service contexts.

    The ServiceBuilder is responsible for:
    - Receiving a fully validated service context from the ServiceOrchestrator
    - Creating the corresponding ServiceInstance database record
    - Executing all feature handlers associated with the service
    - Aggregating feature handler output into one computed structure
    - Persisting the computed result on the ServiceInstance

    All input data is assumed to be validated and structurally correct.
    """

    def __init__(
        self,
        *,
        session: Session,
        selector_engine: SelectorEngine,
        resource_pool_allocator: ResourcePoolAllocator,
    ):
        self.session = session
        self.selector_engine = selector_engine
        self.rpa = resource_pool_allocator

    # ------------------------------------------------------------------ #
    # COMPUTE                                                            #
    # ------------------------------------------------------------------ #
    def compute(self, svc_ctx: dict[str, Any], descriptor: ServiceDescriptor) -> None:
        """
        Compute one service instance from validated service context.
        """
        service_data = svc_ctx["service_data"]

        tenant = service_data["tenant"]        
        svc_name = service_data["service"]
        variant = service_data["variant"]
        
        svc_inst = self._create_service_instance(
            # type=svc_type,
            svc_name=svc_name,
            tenant=tenant,
            variant=variant,
        )

        result = self._run_feature_handlers(
            svc_ctx=svc_ctx,
            descriptor=descriptor,
        )

        svc_inst.computed = result or {}
        self.session.flush()

    # ------------------------------------------------------------------ #
    # INTERNAL HELPERS                                                   #
    # ------------------------------------------------------------------ #
    
    def _create_service_instance(
        self,
        *,
        svc_name: str,
        tenant: str,
        variant: str,
    ) -> ServiceInstance:
        """
        Replace ServiceInstance identified by (svc_name, tenant, variant).
        """

        self.session.execute(
            delete(ServiceInstance).where(
                ServiceInstance.svc_name == svc_name,
                ServiceInstance.tenant == tenant,
                ServiceInstance.variant == variant,
            )
        )

        # Critical: force DELETE to hit the DB before the INSERT
        self.session.flush()

        svc_inst = ServiceInstance(
            svc_name=svc_name,
            tenant=tenant,
            variant=variant,
        )
        self.session.add(svc_inst)
        self.session.flush()

        return svc_inst

    def _run_feature_handlers(
        self,
        *,
        svc_ctx: dict[str, Any],
        descriptor: ServiceDescriptor,
    ) -> dict[str, Any]:
        """
        Load all handler classes, execute them, and deep-merge their outputs.
        """
        result: dict[str, Any] = {}

        for dotted_path in descriptor.feature_handlers.values():
            handler_cls = self._import_handler(dotted_path)
            handler = handler_cls(
                session=self.session,
                service_builder=self,
            )

            handle_result = handler.compute(svc_ctx)
            if handle_result:
                result = deep_merge(result, handle_result)

        return result

    @staticmethod
    def _import_handler(dotted_path: str) -> Type:
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)