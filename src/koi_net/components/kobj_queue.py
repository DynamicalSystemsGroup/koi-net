import threading
from dataclasses import dataclass, field
from logging import Logger
from queue import Queue

from rid_lib.core import RID
from rid_lib.ext import Bundle, Manifest
from rid_lib.types import KoiNetNode

from ..protocol.event import Event, EventType
from ..protocol.knowledge_object import KnowledgeObject


@dataclass
class KobjQueue:
    """Queue for knowledge objects entering the processing pipeline."""
    log: Logger
    shutdown_signal: threading.Event
    
    q: Queue[KnowledgeObject] = field(init=False, default_factory=Queue)
    
    def push(
        self, *,
        rid: RID | None = None,
        manifest: Manifest | None = None,
        bundle: Bundle | None = None,
        event: Event | None = None,
        kobj: KnowledgeObject | None = None,
        event_type: EventType | None = None,
        source: KoiNetNode | None = None
    ):
        """Pushes knowledge object to queue.
        
        Input may take the form of an RID, manifest, bundle, event, 
        or knowledge object (with an optional event type for RID, 
        manifest, or bundle objects). All objects will be normalized 
        to knowledge objects and queued.
        """
        
        if rid:
            _kobj = KnowledgeObject.from_rid(rid, event_type, source)
        elif manifest:
            _kobj = KnowledgeObject.from_manifest(manifest, event_type, source)
        elif bundle:
            _kobj = KnowledgeObject.from_bundle(bundle, event_type, source)
        elif event:
            _kobj = KnowledgeObject.from_event(event, source)
        elif kobj:
            _kobj = kobj
        else:
            raise ValueError("One of 'rid', 'manifest', 'bundle', 'event', or 'kobj' must be provided")
        
        self.q.put(_kobj)
        self.log.debug(f"Queued {_kobj!r}")
    
    def wait(self):
        """Safe join, prevents deadlock if `kobj_worker` fails."""
        while not self.shutdown_signal.wait(0.1):
            if self.q.unfinished_tasks == 0:
                return
        
        raise RuntimeError("Shutdown while awaiting queue")