from dataclasses import dataclass, field
from logging import Logger

from rid_lib.types import KoiNetNode

from koi_net.protocol.errors import ErrorType
from koi_net.protocol.event import EventType

from .kobj_queue import KobjQueue


@dataclass
class ErrorHandler:
    """Handles network and protocol errors that may occur during requests."""
    log: Logger
    kobj_queue: KobjQueue
    
    timeout_counter: dict[KoiNetNode, int] = field(init=False, default_factory=dict)
    
    def reset_timeout_counter(self, node: KoiNetNode):
        """Reset's a node timeout counter to zero."""
        self.timeout_counter[node] = 0
    
    def handle_connection_error(self, node: KoiNetNode):
        """Drops nodes after timing out three times.
        
        TODO: Need a better heuristic for network state. For example, if
        a node lost connection to the internet, it would quickly forget
        all other nodes.
        """
        self.timeout_counter.setdefault(node, 0)
        self.timeout_counter[node] += 1
        
        self.log.debug(f"{node} has timed out {self.timeout_counter[node]} time(s)")
        
        if self.timeout_counter[node] > 3:
            self.log.debug(f"Exceeded time out limit, forgetting node")
            self.kobj_queue.push(rid=node, event_type=EventType.FORGET)
        
    def handle_protocol_error(
        self, 
        error_type: ErrorType, 
        node: KoiNetNode
    ):
        """Handles protocol errors that occur during network requests.
        
        Attempts handshake when this node is unknown to target.
        """
        
        self.log.info(f"Handling protocol error {error_type} for node {node!r}")
        match error_type:
            case ErrorType.UnknownNode: ...
            case ErrorType.InvalidKey: ...
            case ErrorType.InvalidSignature: ...
            case ErrorType.InvalidTarget: ...
