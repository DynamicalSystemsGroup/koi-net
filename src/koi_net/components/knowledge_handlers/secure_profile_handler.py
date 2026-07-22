from dataclasses import dataclass

from rid_lib.types import KoiNetNode
from rid_lib.ext.utils import sha256_hash

from koi_net.protocol.knowledge_object import KnowledgeObject
from koi_net.protocol.event import EventType
from koi_net.protocol.node import NodeProfile
from ..identity import NodeIdentity
from ..interfaces import KnowledgeHandler, STOP_CHAIN, HandlerType


@dataclass
class SecureProfileHandler(KnowledgeHandler):
    """Validates the identity and public keys of incoming nodes.
    
    Interrupts knowledge processing for node profiles which have a mismatched
    public key and hash, or using the same base url as this node.
    """
    
    identity: NodeIdentity
    
    handler_type = HandlerType.Bundle
    rid_types = (KoiNetNode,)
    event_types = (EventType.NEW, EventType.UPDATE)
    
    def handle(self, kobj: KnowledgeObject):
        node_profile = kobj.bundle.validate_contents(NodeProfile)
        node_rid: KoiNetNode = kobj.rid
        
        if sha256_hash(node_profile.public_key) != node_rid.hash:
            self.log.warning(f"Public key hash mismatch for {node_rid!r}!")
            return STOP_CHAIN
        
        if (node_rid != self.identity.rid) and (node_profile.base_url == self.identity.profile.base_url):
            self.log.warning(f"Ignoring node claiming same base URL: {node_profile.base_url}")
            return STOP_CHAIN
