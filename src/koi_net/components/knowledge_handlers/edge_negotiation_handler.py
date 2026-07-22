from dataclasses import dataclass

from rid_lib.ext import Bundle
from rid_lib.types import KoiNetEdge, KoiNetNode

from koi_net.protocol.node import NodeProfile, NodeType
from koi_net.protocol.edge import EdgeProfile, EdgeStatus, EdgeType
from koi_net.protocol.knowledge_object import KnowledgeObject
from koi_net.protocol.event import Event, EventType
from ..interfaces import KnowledgeHandler, STOP_CHAIN, HandlerType
from ..identity import NodeIdentity
from ..kobj_queue import KobjQueue
from ..event_queue import EventQueue
from ..cache import Cache


@dataclass
class EdgeNegotiationHandler(KnowledgeHandler):
    """Handles edge negotiation process.
    
    Automatically approves proposed edges if they request RID types this
    node can provide (or KOI node, edge RIDs). Validates the edge type
    is allowed for the node type (partial nodes cannot use webhooks). If
    edge is invalid, a :attr:`~koi_net.protocol.event.EventType.FORGET`
    event is sent to the other node.
    """
    
    identity: NodeIdentity
    cache: Cache
    event_queue: EventQueue
    kobj_queue: KobjQueue
    
    handler_type = HandlerType.Bundle
    rid_types = (KoiNetEdge,)
    event_types = (EventType.NEW, EventType.UPDATE)
    
    def handle(self, kobj: KnowledgeObject):
        # only handle incoming events (ignore internal edge knowledge objects)
        if kobj.source is None: 
            return
        
        edge_profile = kobj.bundle.validate_contents(EdgeProfile)

        # indicates peer subscribing to this node
        if edge_profile.source == self.identity.rid:
            if edge_profile.status != EdgeStatus.PROPOSED:
                return
            
            self.log.debug("Handling edge negotiation")
            
            peer_rid = edge_profile.target
            peer_bundle = self.cache.read(peer_rid)
            
            if not peer_bundle:
                self.log.warning(f"Peer {peer_rid!r} unknown to me")
                return STOP_CHAIN
            
            peer_profile = peer_bundle.validate_contents(NodeProfile)
            
            # explicitly provided event RID types and (self) node + edge objects
            provided_events = (
                *self.identity.profile.provides.event,
                KoiNetNode, KoiNetEdge
            )
            
            abort = False
            if (edge_profile.edge_type == EdgeType.WEBHOOK and 
                peer_profile.node_type == NodeType.PARTIAL):
                self.log.debug("Partial nodes cannot use webhooks")
                abort = True
            
            if not set(edge_profile.rid_types).issubset(provided_events):
                not_provided = set(edge_profile.rid_types) - set(provided_events)
                self.log.debug(f"Requested RID types {not_provided} not provided by this node")
                abort = True
            
            if abort:
                event = Event.from_rid(EventType.FORGET, kobj.rid)
                self.event_queue.push(event, peer_rid)
                return STOP_CHAIN
            
            else:
                self.log.debug("Approving proposed edge")
                edge_profile.status = EdgeStatus.APPROVED
                updated_bundle = Bundle.generate(kobj.rid, edge_profile.model_dump())

                self.kobj_queue.push(bundle=updated_bundle, event_type=EventType.UPDATE)
                return
                
        elif edge_profile.target == self.identity.rid:
            if edge_profile.status == EdgeStatus.APPROVED:
                self.log.debug("Edge approved by other node!")

