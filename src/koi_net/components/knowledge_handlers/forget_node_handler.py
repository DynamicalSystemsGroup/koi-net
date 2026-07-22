from dataclasses import dataclass

from rid_lib.types import KoiNetEdge, KoiNetNode

from koi_net.protocol.edge import EdgeProfile
from koi_net.protocol.knowledge_object import KnowledgeObject
from koi_net.protocol.event import EventType
from ..interfaces import KnowledgeHandler, HandlerType
from ..kobj_queue import KobjQueue
from ..cache import Cache


@dataclass
class ForgetNodeHandler(KnowledgeHandler):
    """Removes edges connected to forgotten nodes."""
    
    cache: Cache
    kobj_queue: KobjQueue
    
    handler_type = HandlerType.Final
    rid_types=(KoiNetNode,)
    
    def handle(self, kobj: KnowledgeObject):
        if kobj.normalized_event_type != EventType.FORGET:
            return
        
        for edge_rid in self.cache.list_rids(rid_types=[KoiNetEdge]):
            edge_bundle = self.cache.read(edge_rid)
            if not edge_bundle:
                continue
            
            edge_profile = edge_bundle.validate_contents(EdgeProfile)
            
            if kobj.rid in (edge_profile.source, edge_profile.target):
                self.log.debug("Identified edge with forgotten node")
                self.kobj_queue.push(rid=edge_rid, event_type=EventType.FORGET)