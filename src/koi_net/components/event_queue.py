from dataclasses import dataclass, field
from queue import Queue

from rid_lib.types import KoiNetNode

from koi_net.protocol.event import Event


@dataclass
class QueuedEvent:
    event: Event
    target: KoiNetNode

@dataclass
class EventQueue:
    """Queue for outgoing network events."""
    
    q: Queue[QueuedEvent] = field(init=False, default_factory=Queue)
    
    def push(self, event: Event, target: KoiNetNode):
        """Pushes event to queue of specified node.
        
        Event will be sent to webhook or poll queue by the event worker
        depending on the node type and edge type of the specified node.
        """
        
        self.q.put(QueuedEvent(target=target, event=event))
    