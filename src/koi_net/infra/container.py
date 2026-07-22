import time
import threading
from queue import Queue
from typing import TYPE_CHECKING, Any
from pathlib import Path
from logging import Logger

from .lifecycle import NodeLifecycle, NodeState
from .build_artifact import BuildArtifact

if TYPE_CHECKING:
    from ..components import LoggingContext


class NodeContainer:
    """Container object returned by assembler, contains components, exposes
    lifecycle methods.

    This class expects the following components to exist, which MUST be
    included in any assembly: :attr:`.log`, :attr:`.root_dir`,
    :attr:`.logging_context`, :attr:`.shutdown_signal`, and
    :attr:`.exception_queue`. :class:`~koi_net.base.BaseAssembly` is a base
    class implementing these components for that purpose.

    The lifecycle methods exposed by the container proxy to the lifecycle
    object it creates on initialization.
    """
    
    _artifact: BuildArtifact
    _lifecyle: NodeLifecycle

    log: Logger
    root_dir: Path
    logging_context: "LoggingContext"
    shutdown_signal: threading.Event
    exception_queue: Queue[Exception]
    
    def __init__(self, artifact, components: dict[str, Any]):
        self._artifact = artifact
        
        # adds all components as attributes of this instance
        for name, comp in components.items():
            setattr(self, name, comp)
            
        
        self._lifecycle = NodeLifecycle(
            log=self.log,
            logging_context=self.logging_context,
            shutdown_signal=self.shutdown_signal,
            exception_queue=self.exception_queue,
            artifact=self._artifact,
            container=self
        )
    
    def run(self):
        try:
            self.start()
            print("Press Ctrl + C to quit")
            while (self.get_state() is NodeState.RUNNING):
                time.sleep(0.5)
        
        except KeyboardInterrupt:
            print("Quitting...")
        
        finally:
            self.stop()
    
    def start(self, block: bool = True):
        self._lifecycle.start(block=block)
        
    def stop(self, block: bool = True):
        self._lifecycle.stop(block=block)
        
    def get_state(self) -> NodeState:
        return self._lifecycle.state