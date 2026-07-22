import queue
from dataclasses import dataclass

from ..config.base import BaseNodeConfig
from .pipeline import KnowledgePipeline
from .kobj_queue import KobjQueue
from .interfaces import ThreadedComponent
from ..infra import depends_on


class End:
    """Class for STOP_WORKER sentinel pushed to worker queues."""
    pass

STOP_WORKER = End()


@dataclass
class KnowledgeProcessingWorker(ThreadedComponent):
    """Thread worker that processes the :attr:`.kobj_queue`."""
    
    config: BaseNodeConfig
    kobj_queue: KobjQueue
    pipeline: KnowledgePipeline
    
    @depends_on("server", "poller")
    def stop(self):
        self.kobj_queue.q.put(STOP_WORKER)
        super().stop()
        
    def run(self):
        """Main loop of knowledge processing worker thread.
        
        Dequeues knowledge objects and sends them to the knowledge pipeline
        for processing. Gracefully shuts down upon dequeueing
        :obj:`~koi_net.components.kobj_worker.STOP_WORKER` sentinel.
        """
        
        while True:
            try:
                item = self.kobj_queue.q.get(timeout=self.config.koi_net.kobj_worker.queue_timeout)
                try:
                    if item is STOP_WORKER:
                        self.log.info("Received 'STOP_WORKER' signal, shutting down...")
                        return
                    
                    self.log.info(f"Dequeued {item!r}")
                    self.pipeline.process(item)
                    
                finally:
                    self.kobj_queue.q.task_done()
                    
            except queue.Empty:
                pass

