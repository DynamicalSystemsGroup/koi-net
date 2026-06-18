from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from rid_lib import RID, RIDType
from rid_lib.ext.bundle import Bundle
from rid_lib.ext.utils import sha256_hash
from rid_lib.types import KoiNetEdge, KoiNetNode


class EdgeStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    
class EdgeType(StrEnum):
    WEBHOOK = "WEBHOOK"
    POLL = "POLL"

class EdgeProfile(BaseModel):
    context: RID = Field(
        alias="@context", 
        default="orn:koi-net.context:koi-net.edge")
    source: KoiNetNode
    target: KoiNetNode
    edge_type: EdgeType
    status: EdgeStatus
    rid_types: list[RIDType]
    
    model_config = ConfigDict(
        serialize_by_alias=True,
        validate_by_name=True,
    )


def generate_edge_bundle(
    source: KoiNetNode,
    target: KoiNetNode,
    rid_types: list[RIDType],
    edge_type: EdgeType
) -> Bundle:
    """Returns edge bundle."""
    
    edge_rid = KoiNetEdge(sha256_hash(
        str(source) + str(target)
    ))
    
    edge_profile = EdgeProfile(
        source=source,
        target=target,
        rid_types=rid_types,
        edge_type=edge_type,
        status=EdgeStatus.PROPOSED
    )
    
    edge_bundle = Bundle.generate(
        edge_rid,
        edge_profile.model_dump()
    )
    
    return edge_bundle