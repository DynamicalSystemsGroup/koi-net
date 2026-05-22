from dataclasses import dataclass

from rid_lib.ext import Bundle
from rid_lib.types import KoiNetNode

from koi_net.exceptions import RequestError
from koi_net.config.base import BaseNodeConfig
from koi_net.infra import depends_on
from koi_net.protocol.node import NodeProfile, NodeType
from koi_net.protocol.edge import EdgeProfile, EdgeStatus, EdgeType, generate_edge_bundle
from koi_net.protocol.knowledge_object import KnowledgeObject
from ..interfaces import KnowledgeHandler, HandlerType
from ..identity import NodeIdentity
from ..kobj_queue import KobjQueue
from ..cache import Cache
from ..request_handler import RequestHandler
from ..graph import NetworkGraph


@dataclass
class NodeContactHandler(KnowledgeHandler):
    identity: NodeIdentity
    cache: Cache
    config: BaseNodeConfig
    kobj_queue: KobjQueue
    graph: NetworkGraph
    request_handler: RequestHandler
    
    handler_type = HandlerType.Network
    rid_types = (KoiNetNode,)
    
    def process_node(self, node_rid: KoiNetNode, node_bundle: Bundle):
        # prevents nodes from attempting to form a self loop
        if node_rid == self.identity.rid:
            return
        
        node_profile = node_bundle.validate_contents(NodeProfile)
        
        if node_profile.node_type is NodeType.PARTIAL:
            return
        
        # None indicates interest in all types, while an empty list would indicate interest in no types
        if self.config.koi_net.rid_types_of_interest is None:
            available_rid_types = node_profile.provides.event
        
        else:
            available_rid_types = list(
                set(self.config.koi_net.rid_types_of_interest) & 
                set(node_profile.provides.event)
            )
            
        if not available_rid_types:
            return
        
        edge_rid = self.graph.get_edge(
            source=node_rid,
            target=self.identity.rid,
        )
        
        # already have an edge established
        if edge_rid:
            prev_edge_bundle = self.cache.read(edge_rid)
            edge_profile = prev_edge_bundle.validate_contents(EdgeProfile)
            
            if set(edge_profile.rid_types) == set(available_rid_types):
                # no change in rid types
                return
            
            self.log.info(f"Proposing updated edge with node provider {available_rid_types}")
            
            edge_profile.rid_types = available_rid_types
            edge_profile.status = EdgeStatus.PROPOSED
            edge_bundle = Bundle.generate(edge_rid, edge_profile.model_dump())
        
        # no existing edge
        else:
            self.log.info(f"Proposing new edge with node provider {available_rid_types}")
            edge_bundle = generate_edge_bundle(
                source=node_rid,
                target=self.identity.rid,
                rid_types=available_rid_types,
                edge_type=(
                    EdgeType.WEBHOOK
                    if self.identity.profile.node_type == NodeType.FULL
                    else EdgeType.POLL
                )
            )
        
        # queued for processing
        self.kobj_queue.push(bundle=edge_bundle)
        
        self.log.info("Catching up on network state")
        try:
            payload = self.request_handler.fetch_rids(
                node=node_rid, 
                rid_types=available_rid_types
            )
        except RequestError:
            self.log.info("Failed to reach node")
            return
            
        for rid in payload.rids:
            if rid == self.identity.rid:
                self.log.info("Skipping myself")
                continue
            if self.cache.exists(rid):
                self.log.info(f"Skipping known RID {rid!r}")
                continue
            
            # marked as external since we are handling RIDs from another node
            # will fetch remotely instead of checking local cache
            self.kobj_queue.push(rid=rid, source=node_rid)
        self.log.info("Done")
    
    def handle(self, kobj: KnowledgeObject):
        """Makes contact with providers of RID types of interest.
        
        When an incoming node knowledge object is identified as a provider
        of an RID type of interest, this handler will propose a new edge 
        subscribing to future node events, and fetch existing nodes to catch 
        up to the current state.
        """
        self.process_node(kobj.rid, kobj.bundle)
    
    @depends_on("graph", "kobj_worker", "handshaker")
    def start(self):
        self.log.info("Starting node contact analysis on cached profiles...")
        for rid in self.cache.list_rids(rid_types=(KoiNetNode,)):
            bundle = self.cache.read(rid)
            if not bundle:
                continue
            
            self.process_node(rid, bundle)