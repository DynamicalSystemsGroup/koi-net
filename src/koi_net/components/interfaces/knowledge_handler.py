from dataclasses import dataclass, field
from enum import StrEnum
from logging import Logger
from typing import TYPE_CHECKING
from rid_lib.core import RIDType

from koi_net.protocol.event import EventType
from koi_net.protocol.knowledge_object import KnowledgeObject

if TYPE_CHECKING:
    from ..pipeline import KnowledgePipeline


class StopChain:
    """Class for STOP_CHAIN sentinel returned by knowledge handlers."""
    pass

STOP_CHAIN = StopChain()

class HandlerType(StrEnum):
    """Types of handlers used in knowledge processing pipeline.
    
    - RID - provided RID; if event type is `FORGET`, this handler decides 
    whether to delete the knowledge from the cache by setting the normalized event type to `FORGET`, otherwise this handler decides whether to validate the manifest (and fetch it if not provided).
    - Manifest - provided RID, manifest; decides whether to validate the bundle (and fetch it if not provided).
    - Bundle - provided RID, manifest, contents (bundle); decides whether to write knowledge to the cache by setting the normalized event type to `NEW` or `UPDATE`.
    - Network - provided RID, manifest, contents (bundle); decides which nodes (if any) to broadcast an event about this knowledge to. (Note, if event type is `FORGET`, the manifest and contents will be retrieved from the local cache, and indicate the last state of the knowledge before it was deleted.)
    - Final - provided RID, manifests, contents (bundle); final action taken after network broadcast.
    """
    
    RID = "rid", 
    Manifest = "manifest", 
    Bundle = "bundle", 
    Network = "network", 
    Final = "final"

@dataclass
class KnowledgeHandler:
    """Base class for knowledge processing pipeline handler components.
    
    Derived classes MUST define the class variable `handler_type`, and
    may optionally set `rid_types` and `event_types`, to limit when, and
    which kind of knowledge objects will be passed to this handler.
    """
    
    log: Logger
    pipeline: "KnowledgePipeline"
    
    handler_type: HandlerType = field(init=False)
    rid_types: tuple[RIDType] = field(init=False, default=())
    event_types: tuple[EventType | None] = field(init=False, default=())
    
    def __post_init__(self):
        self.pipeline.register_handler(self)
    
    def handle(self, kobj: KnowledgeObject) -> KnowledgeObject | None | StopChain:
        ...
