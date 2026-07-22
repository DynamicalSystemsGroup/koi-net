import time
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Generator
from rid_lib.types import KoiNetNode

from koi_net.protocol.event import Event


@dataclass
class EventBuffer:
    """Stores outgoing events sent to other nodes.
    
    Used for both the poll and broadcast event buffer components.
    """

    buffers: dict[KoiNetNode, list[Event]] = field(init=False, default_factory=dict)
    start_time: dict[KoiNetNode, float] = field(init=False, default_factory=dict)

    def push(self, node: KoiNetNode, event: Event):
        """Pushes event to specified node.
        
        Sets start time to now if unset.
        """
        
        self.start_time.setdefault(node, time.time())
        
        event_buf = self.buffers.setdefault(node, [])
        event_buf.append(event)
        
    def buf_len(self, node: KoiNetNode):
        """Returns the length of a node's event buffer."""
        return len(self.buffers.get(node, []))
        
    def flush(self, node: KoiNetNode, limit: int = 0) -> list[Event]:
        """Flushes all (or limit) events for a node.
        
        Resets start time.
        """
        self.start_time.pop(node, None)
        
        if node not in self.buffers:
            return []
        
        event_buf = self.buffers[node]
        
        if limit and len(event_buf) > limit:
            flushed_events = event_buf[:limit]
            self.buffers[node] = event_buf[limit:]
        else:
            flushed_events = event_buf.copy()
            del self.buffers[node]
        
        return flushed_events
    
    @contextmanager
    def safe_flush(
        self, 
        node: KoiNetNode, 
        limit: int = 0,
        force_flush: bool = False
    ) -> Generator[list[Event], None, None]:
        """Context managed safe flush, only commits on successful exit.
        
        Exceptions will result in buffer rollback to the previous state.
        """
        
        self.start_time.pop(node, None)
        
        if node not in self.buffers:
            yield []
            return
        
        event_buf = self.buffers[node].copy()
        in_place = limit and len(event_buf) > limit
        
        try:
            if in_place:
                yield event_buf[:limit]
                self.buffers[node] = event_buf[limit:]
            else:
                yield event_buf.copy()
                self.buffers.pop(node, None)
        
        except Exception:
            # if force, flushes buffers and reraises exception
            if force_flush:
                if in_place:
                    self.buffers[node] = event_buf[limit:]
                else:
                    self.buffers.pop(node, None)
            raise
