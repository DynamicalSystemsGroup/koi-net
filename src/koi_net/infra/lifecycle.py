import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from logging import Logger
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.traceback import Traceback

from .build_artifact import BuildArtifact
from .consts import START_FUNC_NAME, STOP_FUNC_NAME

if TYPE_CHECKING:
    from koi_net.components import LoggingContext


class NodeState(StrEnum):
    """Represents state throughout the node container lifecycle."""
    
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"

@dataclass
class NodeLifecycle:
    """Manages the lifecycle of a node conatiner, and the components within it."""
    
    log: Logger
    shutdown_signal: threading.Event
    exception_queue: Queue[Exception]
    logging_context: "LoggingContext"
    artifact: BuildArtifact
    container: Any
    
    state: NodeState = field(init=False, default=NodeState.IDLE)
    thread: threading.Thread | None = field(init=False, default=None)
    startup_signal: threading.Event = field(init=False, default_factory=threading.Event)
    
    def start(self, block: bool = True):
        """Starts the lifecycle manager thread, beginning node startup."""
        
        if self.state != NodeState.IDLE:
            self.log.warning("Node can't be started from non-idle state")
            return
        
        self.startup_signal.clear()
        self.thread = threading.Thread(target=self._run)
        self.thread.start()
        
        if block:
            self.startup_signal.wait()
        
    def stop(self, block: bool = True):
        """Signals to lifecycle manager thread, beginning node shutdown."""
        
        if self.state != NodeState.RUNNING:
            self.log.warning("Node can't be stopped from non-running state")
            return
        
        self.shutdown_signal.set()
        
        if block and self.thread and self.thread.is_alive():
            self.thread.join()

    def _run(self):
        """The method run in the lifecycle's main thread.
        
        Handles component startup, shutdown, and any exceptions pushed
        into the exception queue.
        """
        with self.logging_context.bound_vars(thread=self.__class__.__name__):
            try:
                self._startup()
                self.startup_signal.set()
                # awaits shutdown signal after startup
                self.shutdown_signal.wait()
                
            finally:
                # attempts to call shutdown, even if unhandled exception
                # thrown during startup
                self._shutdown()
                
                while True:
                    # prints all queued exceptions before exiting the thread
                    try:
                        exc = self.exception_queue.get_nowait()
                        traceback = Traceback.from_exception(
                            exc_type=type(exc),
                            exc_value=exc,
                            traceback=exc.__traceback__
                        )
                        print()
                        Console().print(traceback)
                        
                    except Empty:
                        break
        
    def _startup(self):
        """Starts up all components, and queues any exceptions that occur."""
        
        self.state = NodeState.STARTING
        self.log.info("Starting node...")
        for comp_name in self.artifact.start_order:
            comp = getattr(self.container, comp_name)
            start_func = getattr(comp, START_FUNC_NAME)
            self.log.info(f"Starting {comp_name}...")
            
            try:
                start_func()
            except Exception as err:
                print()
                self.log.error("Startup error: " + str(err))
                self.exception_queue.put(err)
                self.shutdown_signal.set()
            
            if self.shutdown_signal.is_set():
                self.log.error(f"Startup failed, aborting")
                return
        
        self.state = NodeState.RUNNING
        self.log.info("Startup complete!")
            
    def _shutdown(self):
        """Shuts down all components, and queues any exceptions that occur."""
        
        self.state = NodeState.STOPPING
        self.log.info("Stopping node...")
        for comp_name in self.artifact.stop_order:
            comp = getattr(self.container, comp_name)
            stop_func = getattr(comp, STOP_FUNC_NAME)
            self.log.info(f"Stopping {comp_name}...")
            
            try:
                stop_func()
            except Exception as err:
                self.log.error("Shutdown error:", str(err))
                self.exception_queue.put(err)
        
        self.shutdown_signal.clear()
        self.state = NodeState.IDLE
        self.log.info("Shutdown complete!")

