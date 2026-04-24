from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ServiceDefinitionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    service: str
    tenant: str
    variant: str

    selectors: dict[str, Any] 

    features: dict[str, Any] 

    interface_features: dict[str, Any]

    parameters: dict[str, Any]







