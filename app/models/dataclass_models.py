from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class RoleView:
    name: str


@dataclass(frozen=True)
class DeviceSelectorView:
    hostname: str
    labels: Mapping[str, str]
    role: RoleView


@dataclass(frozen=True, slots=True)
class ServiceDescriptor:
    """
    Describes a service type known to the Service Orchestrator.

    - name: Service name (i.e.: isis, bgp, etc)
    - definition_schema: Pydantic model for service definition validation    
    - feature_handlers: mapping of feature-name -> handler import path
    """

    name: str
    definition_schema: Type[BaseModel]
    feature_handlers: dict[str, str]
