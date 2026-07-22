from dataclasses import dataclass
from pathlib import Path

from structlog.contextvars import bound_contextvars


@dataclass
class LoggingContext:
    """Provides access to context vars setting the correct file path
    for a node's logs in tandem with the log system.
    
    Mostly used behind the scenes to ensure that logs within other
    threads and contexts are correctly routed. It is called by the
    base :class:`~koi_net.components.interfaces.threaded_component.ThreadedComponent`
    class, and :class:`~koi_net.infra.lifecycle.NodeLifecycle`.
    """
    
    root_dir: Path
    
    def bound_vars(self, thread: str):
        return bound_contextvars(log_dir=self.root_dir, thread=thread)