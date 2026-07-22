from dataclasses import dataclass

from koi_net.protocol.knowledge_object import KnowledgeObject
from koi_net.protocol.event import EventType
from ..interfaces import KnowledgeHandler, STOP_CHAIN, HandlerType
from ..cache import Cache


@dataclass
class BasicManifestHandler(KnowledgeHandler):
    """Normalized event decider based on manifest and cache state.

    Stops processing for manifests which have the same hash, or aren't
    newer than the cached version. Sets the normalized event type to
    :attr:`~koi_net.protocol.event.EventType.NEW` or
    :attr:`~koi_net.protocol.event.EventType.UPDATE` depending on whether the
    RID was previously known.
    """
    
    cache: Cache
    
    handler_type = HandlerType.Manifest
    
    def handle(self, kobj: KnowledgeObject):
        prev_bundle = self.cache.read(kobj.rid)

        if prev_bundle:
            if kobj.manifest.sha256_hash == prev_bundle.manifest.sha256_hash:
                self.log.debug("Hash of incoming manifest is same as existing knowledge, ignoring")
                return STOP_CHAIN
            if kobj.manifest.timestamp <= prev_bundle.manifest.timestamp:
                self.log.debug("Timestamp of incoming manifest is the same or older than existing knowledge, ignoring")
                return STOP_CHAIN
            
            self.log.debug("RID previously known to me, labeling as 'UPDATE'")
            kobj.normalized_event_type = EventType.UPDATE

        else:
            self.log.debug("RID previously unknown to me, labeling as 'NEW'")
            kobj.normalized_event_type = EventType.NEW
            
        return kobj