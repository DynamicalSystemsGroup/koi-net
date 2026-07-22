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

    See :class:`~koi_net.components.pipeline.KnowledgePipeline` for the
    differences between handler types.
    """
    
    RID = "rid", 
    Manifest = "manifest", 
    Bundle = "bundle", 
    Network = "network", 
    Final = "final"

@dataclass
class KnowledgeHandler:
    """Base class for knowledge processing pipeline handler components.

    Derived classes MUST define the class variable :attr:`.handler_type`, and
    may optionally set :attr:`.rid_types` and :attr:`.event_types`, to limit
    when, and which kind of knowledge objects will be passed to this handler.
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
