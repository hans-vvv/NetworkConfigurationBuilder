from typing import Any

from pydantic import BaseModel, ConfigDict


class AddressingFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loopback0: dict[str, Any]    
    p2p: dict[str, Any]


class AddressingPolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    selectors: dict[str, Any]
    features: dict[str, AddressingFeature]
