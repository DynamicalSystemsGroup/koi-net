from dataclasses import dataclass

from rid_lib.types import KoiNetNode

from ..config.base import BaseNodeConfig
from ..protocol.node import NodeProfile


@dataclass
class NodeIdentity:
    """Proxied access to a node's identity (RID, profile)."""
    
    config: BaseNodeConfig
    
    @property
    def rid(self) -> KoiNetNode:
        return self.config.koi_net.node_rid
    
    @property
    def profile(self) -> NodeProfile:
        return self.config.koi_net.node_profile
