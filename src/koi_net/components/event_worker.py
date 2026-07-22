import queue
import time
from dataclasses import dataclass

from rid_lib.ext import Cache
from rid_lib.types import KoiNetNode

from ..infra import depends_on
from ..config.base import BaseNodeConfig
from ..protocol.node import NodeProfile, NodeType
from ..exceptions import RequestError

from .event_queue import EventQueue
from .request_handler import RequestHandler
from .event_buffer import EventBuffer
from .interfaces import ThreadedComponent


class End:
    """Class for :obj:`~koi_net.components.event_worker.STOP_WORKER` sentinel
    pushed to worker queues."""
    pass

STOP_WORKER = End()


@dataclass
class EventProcessingWorker(ThreadedComponent):
    """Thread worker that processes the :attr:`.event_queue`."""
    
    config: BaseNodeConfig
    cache: Cache
    event_queue: EventQueue
    request_handler: RequestHandler
    poll_event_buf: EventBuffer
    broadcast_event_buf: EventBuffer
        
    def flush_and_broadcast(self, target: KoiNetNode, force_flush: bool = False):
        """Broadcasts all events to target in event buffer."""
        
        # TODO: deal with automated retries when unreachable node's buffer is full
        try:
            with self.broadcast_event_buf.safe_flush(target, force_flush) as events:
                self.request_handler.broadcast_events(target, events=events)
        except RequestError:
            self.log.warning("Failed to reach target, event buffer reset")
            pass
    
    @depends_on("kobj_worker")
    def stop(self):
        """Signals thread to shutdown at end of queue via sentinel."""
        
        self.event_queue.q.put(STOP_WORKER)
        super().stop()
    
    def run(self):
        """Main loop of event worker thread.
        
        Dequeues events from :attr:`.event_queue` and pushes them to
        :attr:`.poll_event_buf` or :attr:`.broadcast_event_buf` depending on
        the node type. Special handling for communication with first contact
        node, which is assumed to be a full node if its profile cannot
        be found.

        Automatically flushes :attr:`.broadcast_event_buf` when it reaches
        max length, or max wait time.

        Gracefully shuts down upon dequeueing
        :obj:`~koi_net.components.event_worker.STOP_WORKER` sentinel.
        """
        
        while True:
            try:
                item = self.event_queue.q.get(
                    timeout=self.config.koi_net.event_worker.queue_timeout)
                
                try:
                    if item is STOP_WORKER:
                        self.log.info(f"Received 'STOP_WORKER' signal, flushing all buffers...")
                        for target in list(self.broadcast_event_buf.buffers.keys()):
                            self.flush_and_broadcast(target, force_flush=True)
                        return
                    
                    self.log.info(f"Dequeued {item.event!r} -> {item.target!r}")
                    
                    # determines which buffer to push event to based on target node type
                    node_bundle = self.cache.read(item.target)
                    if node_bundle:
                        node_profile = node_bundle.validate_contents(NodeProfile)
                        
                        if node_profile.node_type == NodeType.FULL:
                            self.broadcast_event_buf.push(item.target, item.event)
                            
                        elif node_profile.node_type == NodeType.PARTIAL:
                            self.poll_event_buf.push(item.target, item.event)
                            continue
                        
                    elif item.target == self.config.koi_net.first_contact.rid:
                        self.broadcast_event_buf.push(item.target, item.event)
                        
                    else:
                        self.log.warning(f"Couldn't handle event {item.event!r} in queue, node {item.target!r} unknown to me")
                        continue
                    
                    buf_len = self.broadcast_event_buf.buf_len(item.target)
                    if buf_len > self.config.koi_net.event_worker.max_buf_len:
                        self.flush_and_broadcast(item.target)

                finally:
                    self.event_queue.q.task_done()

            except queue.Empty:
                # On timeout, check all buffers for max wait time
                for target in list(self.broadcast_event_buf.buffers):
                    start_time = self.broadcast_event_buf.start_time.get(target)
                    
                    if (start_time is None) or (self.broadcast_event_buf.buf_len(target) == 0):
                        continue
                    
                    now = time.time()
                    if (now - start_time) >= self.config.koi_net.event_worker.max_wait_time: 
                        self.flush_and_broadcast(target)
