
import time
import threading
from dataclasses import dataclass, field

from ..infra import depends_on
from .interfaces import ThreadedComponent

from .kobj_queue import KobjQueue
from .resolver import NetworkResolver
from koi_net.config.partial_node import PartialNodeConfig


@dataclass
class NodePoller(ThreadedComponent):
    """Entry point for partial nodes, manages polling event loop."""
    
    config: PartialNodeConfig
    kobj_queue: KobjQueue
    resolver: NetworkResolver

    exit_event: threading.Event = field(init=False, default_factory=threading.Event)
    
    def poll(self):
        """Polls neighbor nodes and processes returned events."""
        for node_rid, events in self.resolver.poll_neighbors().items():
            for event in events:
                self.kobj_queue.push(event=event, source=node_rid)

    def run(self):
        """Runs polling event loop."""
        while not self.exit_event.is_set():
            start_time = time.monotonic()
            self.poll()
            elapsed = time.monotonic() - start_time
            wait_time = max(0, self.config.poller.polling_interval - elapsed)
            self.exit_event.wait(wait_time)
    
    @depends_on("graph", "profile_monitor")
    def start(self):
        self.exit_event.clear()
        super().start()
    
    def stop(self):
        self.exit_event.set()
        super().stop()