from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from rid_lib import RID, RIDType


class NodeType(StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"

class NodeProvides(BaseModel):
    event: list[RIDType] = []
    state: list[RIDType] = []

class NodeProfile(BaseModel):
    context: RID = Field(
        alias="@context", 
        default="orn:koi-net.context:koi-net.node")
    base_url: str | None = None
    node_type: NodeType
    provides: NodeProvides = NodeProvides()
    public_key: str | None = None
    
    model_config = ConfigDict(
        serialize_by_alias=True,
        validate_by_name=True
    )