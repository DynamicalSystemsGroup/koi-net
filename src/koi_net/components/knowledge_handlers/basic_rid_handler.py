from dataclasses import dataclass

from koi_net.protocol.knowledge_object import KnowledgeObject
from koi_net.protocol.event import EventType
from ..interfaces import KnowledgeHandler, STOP_CHAIN, HandlerType
from ..identity import NodeIdentity


@dataclass
class BasicRidHandler(KnowledgeHandler):
    """Blocks external events about a node's identity, approves FORGET event
    which will then skip any manifest handlers."""
    
    identity: NodeIdentity
    
    handler_type = HandlerType.RID
    
    def handle(self, kobj: KnowledgeObject):
        if kobj.rid == self.identity.rid and kobj.source is not None:
            return STOP_CHAIN
        
        if kobj.event_type == EventType.FORGET:
            kobj.normalized_event_type = EventType.FORGET
            return kobj