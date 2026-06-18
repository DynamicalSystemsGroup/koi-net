from dataclasses import dataclass
from logging import Logger
from rid_lib import RIDType
from rid_lib.ext import Cache
from rid_lib.types import KoiNetNode

from ..config.base import BaseNodeConfig
from ..infra import depends_on
from ..exceptions import RequestError
from .graph import NetworkGraph
from .request_handler import RequestHandler
from .kobj_queue import KobjQueue
from ..protocol.node import NodeProfile, NodeType


@dataclass
class SyncManager:
    """Handles state synchronization actions with other nodes."""
    
    log: Logger
    graph: NetworkGraph
    cache: Cache
    config: BaseNodeConfig
    request_handler: RequestHandler
    kobj_queue: KobjQueue
    
    @depends_on("graph", "kobj_worker", "handshaker")
    def start(self):
        """Catches up with providers on startup."""
        self.catch_up_with_all(self.config.koi_net.rid_types_of_interest)
    
    def catch_up_with_all(self, rid_types: list[RIDType]):
        node_providers = []
        for rid_type in rid_types:
            node_providers = self.graph.get_neighbors(
                direction="in",
                allowed_type=rid_type
            )
            
            if not node_providers:
                continue
            
            self.log.debug(f"Catching up with {rid_type} providers: {node_providers}")
            self.catch_up_with(node_providers, [rid_type])
    
    def catch_up_with(self, nodes: list[KoiNetNode], rid_types: list[RIDType]):
        """Catches up with the state of RID types within other nodes."""
    
        for node in nodes:
            node_bundle = self.cache.read(node)
            node_profile = node_bundle.validate_contents(NodeProfile)
            
            # can't catch up with partial nodes
            if node_profile.node_type != NodeType.FULL:
                continue
            
            try:
                payload = self.request_handler.fetch_manifests(
                    node, rid_types=rid_types)
            except RequestError:
                continue
            
            for manifest in payload.manifests:
                self.kobj_queue.push(
                    manifest=manifest,
                    source=node
                )