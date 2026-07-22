from dataclasses import dataclass, field
from logging import Logger

from rid_lib import RID
from rid_lib.core import RIDType
from rid_lib.ext import Cache, Bundle
from rid_lib.types import KoiNetNode

from .graph import NetworkGraph
from .request_handler import RequestHandler
from ..protocol.node import NodeProfile, NodeType
from ..protocol.event import Event
from .identity import NodeIdentity
from ..config.base import BaseNodeConfig
from ..exceptions import ProtocolError, RequestError


@dataclass
class NetworkResolver:
    """Handles resolving nodes or knowledge objects from the network."""
    
    log: Logger
    config: BaseNodeConfig
    cache: Cache
    identity: NodeIdentity
    graph: NetworkGraph
    request_handler: RequestHandler

    poll_event_queue: dict = field(init=False, default_factory=dict)
    webhook_event_queue: dict = field(init=False, default_factory=dict)
    
    def get_state_providers(self, rid_type: RIDType) -> list[KoiNetNode]:
        """Returns list of node RIDs which provide state for specified RID type."""
        
        self.log.debug(f"Looking for state providers of {rid_type}")
        provider_nodes = []
        for node_rid in self.cache.list_rids(rid_types=[KoiNetNode]):
            if node_rid == self.identity.rid:
                continue
            
            node_bundle = self.cache.read(node_rid)
            node_profile = node_bundle.validate_contents(NodeProfile)
            
            if node_profile.node_type != NodeType.FULL:
                continue
            
            if rid_type not in node_profile.provides.state:
                continue
            
            provider_nodes.append(node_rid)
        
        if provider_nodes:
            self.log.debug(f"Found provider(s) {provider_nodes}")
        else:
            self.log.debug("Failed to find providers")
            
        return provider_nodes
            
    def fetch_remote_bundle(self, rid: RID) -> tuple[Bundle | None, KoiNetNode | None]:
        """Attempts to fetch a bundle by RID from known peer nodes."""
        
        self.log.debug(f"Fetching remote bundle {rid!r}")
        remote_bundle, node_rid = None, None
        for node_rid in self.get_state_providers(type(rid)):
            try:
                payload = self.request_handler.fetch_bundles(
                    node=node_rid, rids=[rid])
            except RequestError:
                continue
            
            if payload.bundles:
                remote_bundle = payload.bundles[0]
                self.log.debug(f"Got bundle from {node_rid!r}")
                break
        
        if not remote_bundle:
            self.log.warning("Failed to fetch remote bundle")
            
        return remote_bundle, node_rid
    
    def fetch_remote_manifest(self, rid: RID) -> tuple[Bundle | None, KoiNetNode | None]:
        """Attempts to fetch a manifest by RID from known peer nodes."""
        
        self.log.debug(f"Fetching remote manifest {rid!r}")
        remote_manifest, node_rid = None, None
        for node_rid in self.get_state_providers(type(rid)):
            try:
                payload = self.request_handler.fetch_manifests(
                    node=node_rid, rids=[rid])
            except RequestError:
                continue
            
            if payload.manifests:
                remote_manifest = payload.manifests[0]
                self.log.debug(f"Got bundle from {node_rid!r}")
                break
        
        if not remote_manifest:
            self.log.warning("Failed to fetch remote bundle")
            
        return remote_manifest, node_rid
    
    def poll_neighbors(self) -> dict[KoiNetNode, list[Event]]:
        """Polls all neighbor nodes and returns compiled list of events.

        Neighbor nodes include any node this node shares an edge with,
        or the first contact, if no neighbors are found.

        .. note::
            This function does not poll nodes that don't share edges
            with this node. Events sent by non neighboring nodes will not
            be polled.
        """
        
        neighbors: list[KoiNetNode] = []
        for node_rid in self.graph.get_neighbors():
            node_bundle = self.cache.read(node_rid)
            if not node_bundle: 
                continue
            node_profile = node_bundle.validate_contents(NodeProfile)
            if node_profile.node_type != NodeType.FULL: 
                continue
            neighbors.append(node_rid)
            
        if not neighbors and self.config.koi_net.first_contact.rid:
            neighbors.append(self.config.koi_net.first_contact.rid)
        
        event_dict: dict[KoiNetNode, list[Event]] = {}
        for node_rid in neighbors:
            try:
                payload = self.request_handler.poll_events(
                    node=node_rid, 
                    rid=self.identity.rid
                )
            except RequestError:
                continue
            
            except ProtocolError as err:
                self.log.warning(f"Remote protocol error: {str(err)}")
                continue
                
            self.log.debug(f"Received {len(payload.events)} events from {node_rid!r}")
            event_dict[node_rid] = payload.events
            
        return event_dict