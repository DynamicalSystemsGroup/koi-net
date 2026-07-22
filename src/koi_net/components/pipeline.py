from dataclasses import dataclass, field
from logging import Logger
from rid_lib.types import KoiNetEdge, KoiNetNode
from rid_lib.ext import Cache

from ..exceptions import RequestError
from ..protocol.event import EventType
from .request_handler import RequestHandler
from .event_queue import EventQueue
from .graph import NetworkGraph
from .interfaces import (
    KnowledgeHandler,
    HandlerType, 
    STOP_CHAIN,
    StopChain
)
from ..protocol.knowledge_object import KnowledgeObject


@dataclass
class KnowledgePipeline:
    """The knowledge pipeline, which ties together many systems
    to process knowldge objects.
    """
    
    log: Logger
    cache: Cache
    request_handler: RequestHandler
    event_queue: EventQueue
    graph: NetworkGraph
    
    knowledge_handlers: list[KnowledgeHandler] = field(init=False, default_factory=list)
    
    def register_handler(self, handler: KnowledgeHandler):
        self.knowledge_handlers.append(handler)
        self.log.info(f"Registered knowledge handler {handler.__class__.__name__}")
    
    def call_handler_chain(
        self, 
        handler_type: HandlerType,
        kobj: KnowledgeObject
    ) -> KnowledgeObject | StopChain:
        """Calls handlers of provided type, chaining their inputs and
        outputs together.

        The knowledge object provided when this function is called will
        be passed to the first handler. A handler may return one of three
        types:

        - :class:`~koi_net.protocol.knowledge_object.KnowledgeObject` - to
          modify the knowledge object for the next handler in the chain
        - ``None`` - to keep the same knowledge object for the next handler
          in the chain
        - :obj:`~koi_net.components.interfaces.knowledge_handler.STOP_CHAIN`
          - to stop the handler chain and immediately exit the processing
          pipeline

        Handlers will only be called in the chain if their handler, RID,
        and event type match that of the inputted knowledge object.
        """
        
        for handler in self.knowledge_handlers:
            if handler_type != handler.handler_type: 
                continue
            
            if handler.rid_types and type(kobj.rid) not in handler.rid_types:
                continue
            
            if handler.event_types and kobj.event_type not in handler.event_types:
                continue
            
            self.log.debug(f"Calling {handler_type} handler '{handler.__class__.__name__}'")
            
            resp = handler.handle(kobj.model_copy())
            
            # stops handler chain execution
            if resp is STOP_CHAIN:
                self.log.debug(f"Handler chain stopped by {handler.__class__.__name__}")
                return STOP_CHAIN
            
            # kobj unmodified
            elif resp is None:
                continue
            
            # kobj modified by handler
            elif isinstance(resp, KnowledgeObject):
                kobj = resp
                self.log.debug(f"Knowledge object modified by {handler.__class__.__name__}")
            
            else:
                raise ValueError(f"Handler {handler.__class__.__name__} returned invalid response '{resp}'")
            
        return kobj
    
    def process(self, kobj: KnowledgeObject):
        """Sends a knowledge object through knowledge processing pipeline.

        Handler chains are called in between major events in the
        pipeline, indicated by their handler type. Each handler type is
        guaranteed to have access to certain knowledge, and may affect a
        subsequent action in the pipeline. The five handler types are as
        follows:

        :attr:`~koi_net.components.interfaces.knowledge_handler.HandlerType.RID`
            - Provided ``kobj.rid``.
            - If event type is
              :attr:`~koi_net.protocol.event.EventType.FORGET`, this handler
              decides whether to delete the knowledge from the cache by
              setting the normalized event type to
              :attr:`~koi_net.protocol.event.EventType.FORGET`. If the
              specified knowledge cannot be found in cache, the pipeline
              will exit.
            - Otherwise this handler decides whether to validate the
              manifest (and fetch it if not provided). If the manifest
              cannot be found or fetched from the source node, the pipeline
              will exit.
            - After processing, if event type is
              :attr:`~koi_net.protocol.event.EventType.FORGET`, the
              manifest and contents will be retrieved from the local cache,
              and indicate the last state of the knowledge before it was
              deleted.

        :attr:`~koi_net.components.interfaces.knowledge_handler.HandlerType.Manifest`
            - Provided ``kobj.rid``, ``kobj.manifest``.
            - This handler type is not called when the event type is
              :attr:`~koi_net.protocol.event.EventType.FORGET`.
            - Decides whether to validate the bundle (and fetch it if not
              provided). If the bundle cannot be found or fetched from the
              source node, the pipeline will exit.

        :attr:`~koi_net.components.interfaces.knowledge_handler.HandlerType.Bundle`
            - Provided ``kobj.rid``, ``kobj.manifest``, ``kobj.bundle``.
            - Decides whether to write knowledge to the cache by setting
              the normalized event type to
              :attr:`~koi_net.protocol.event.EventType.NEW` or
              :attr:`~koi_net.protocol.event.EventType.UPDATE`. If the
              normalized event type remains unset, the pipeline will exit.

        :attr:`~koi_net.components.interfaces.knowledge_handler.HandlerType.Network`
            - Provided ``kobj.rid``, ``kobj.manifest``, ``kobj.bundle``.
            - Decides which nodes (if any) to broadcast an event about this
              knowledge to by adding node RIDs to the
              ``kobj.network_targets`` set. If no network targets are set,
              final handlers are still called. An event formed from the
              knowledge object bundle and normalized event will be pushed
              into the event queue for each target node.

        :attr:`~koi_net.components.interfaces.knowledge_handler.HandlerType.Final`
            - Provided ``kobj.rid``, ``kobj.manifest``, ``kobj.bundle``.
            - Final action taken after network broadcast.

        The pipeline may be stopped by any point by a single handler
        returning the
        :obj:`~koi_net.components.interfaces.knowledge_handler.STOP_CHAIN`
        sentinel. In that case, the process will exit immediately. Further
        handlers of that type and later handler chains will not be called.
        """
        
        self.log.debug(f"Handling {kobj!r}")
        kobj = self.call_handler_chain(HandlerType.RID, kobj)
        if kobj is STOP_CHAIN: return
        
        if kobj.event_type == EventType.FORGET:
            bundle = self.cache.read(kobj.rid)
            if not bundle:
                self.log.debug("Local bundle not found")
                return
            
            # the bundle (to be deleted) attached to kobj for downstream analysis
            self.log.debug("Adding local bundle (to be deleted) to knowledge object")
            kobj.manifest = bundle.manifest
            kobj.contents = bundle.contents
            
        else:
            # attempt to retrieve manifest
            if not kobj.manifest:
                self.log.debug("Manifest not found")
                if not kobj.source:
                    return
            
                self.log.debug("Attempting to fetch remote manifest from source")
                try:
                    payload = self.request_handler.fetch_manifests(
                        node=kobj.source,
                        rids=[kobj.rid])
                except RequestError:
                    self.log.debug("Failed to find manifest")
                    return
                
                kobj.manifest = payload.manifests[0]
                
            kobj = self.call_handler_chain(HandlerType.Manifest, kobj)
            if kobj is STOP_CHAIN: return
            
            # attempt to retrieve bundle
            if not kobj.contents:
                self.log.debug("Bundle not found")
                if kobj.source is None:
                    return
                
                self.log.debug("Attempting to fetch remote bundle from source")
                try:
                    payload = self.request_handler.fetch_bundles(
                        node=kobj.source,
                        rids=[kobj.rid]
                    )
                except RequestError:
                    self.log.debug("Failed to find bundle")
                    return
                
                bundle = payload.bundles[0]
                
                if kobj.manifest != bundle.manifest:
                    self.log.warning("Retrieved bundle contains a different manifest")
                
                kobj.manifest = bundle.manifest
                kobj.contents = bundle.contents
                
        kobj = self.call_handler_chain(HandlerType.Bundle, kobj)
        if kobj is STOP_CHAIN: return
            
        if kobj.normalized_event_type == EventType.NEW:
            self.log.info(f"Writing to cache: {kobj!r}")
            self.cache.write(kobj.bundle)
            
        elif kobj.normalized_event_type == EventType.UPDATE:
            self.log.info(f"Writing to cache: {kobj!r}")
            kobj.prev_bundle = self.cache.read(kobj.rid)
            self.cache.write(kobj.bundle)
            
        elif kobj.normalized_event_type == EventType.FORGET:
            self.log.info(f"Deleting from cache: {kobj!r}")
            self.cache.delete(kobj.rid)
            
        else:
            self.log.debug("Normalized event type was not set, no cache or network operations will occur")
            return
        
        if type(kobj.rid) in (KoiNetNode, KoiNetEdge):
            self.log.debug("Change to node or edge, regenerating network graph")
            self.graph.generate()
        
        kobj = self.call_handler_chain(HandlerType.Network, kobj)
        if kobj is STOP_CHAIN: return
        
        if kobj.network_targets:
            self.log.debug(f"Broadcasting event to {len(kobj.network_targets)} network target(s)")
        else:
            self.log.debug("No network targets set")
        
        for node in kobj.network_targets:
            self.event_queue.push(kobj.normalized_event, node)
        
        kobj = self.call_handler_chain(HandlerType.Final, kobj)
