from dataclasses import dataclass, field
from logging import Logger
from typing import Literal

import networkx as nx
from rid_lib import RIDType
from rid_lib.ext import Cache
from rid_lib.types import KoiNetEdge, KoiNetNode

from koi_net.protocol.edge import EdgeProfile, EdgeStatus
from .identity import NodeIdentity


@dataclass
class NetworkGraph:
    """Graph functions for this node's view of its network."""
    
    log: Logger
    cache: Cache
    identity: NodeIdentity
    
    dg: nx.DiGraph = field(init=False, default_factory=nx.DiGraph)
    
    def start(self):
        self.generate()
        
    def generate(self):
        """Generates directed graph from cached KOI nodes and edges."""
        self.log.debug("Generating network graph")
        self.dg.clear()
        for rid in self.cache.list_rids():
            if type(rid) == KoiNetNode:
                self.dg.add_node(rid)
                self.log.debug(f"Added node {rid!r}")
                
            elif type(rid) == KoiNetEdge:
                edge_bundle = self.cache.read(rid)
                if not edge_bundle:
                    self.log.warning(f"Failed to load {rid!r}")
                    continue
                edge_profile = edge_bundle.validate_contents(EdgeProfile)
                self.dg.add_edge(edge_profile.source, edge_profile.target, rid=rid)
                self.log.debug(f"Added edge {rid!r} ({edge_profile.source} -> {edge_profile.target})")
        self.log.debug("Done")
        
    def get_edge(
        self, 
        source: KoiNetNode, 
        target: KoiNetNode
    ) -> KoiNetEdge | None:
        """Returns edge RID given the RIDs of a source and target node."""
        if (source, target) in self.dg.edges:
            edge_data = self.dg.get_edge_data(source, target)
            if edge_data:
                return edge_data.get("rid")

        return None

    def get_edges(
        self,
        direction: Literal["in", "out"] | None = None,
    ) -> list[KoiNetEdge]:
        """Returns edges this node belongs to.

        All edges returned by default, specify ``direction`` to restrict
        to incoming or outgoing edges only.
        """
        
        edges = []
        if (direction is None or direction == "out") and self.dg.out_edges:
            out_edges = self.dg.out_edges(self.identity.rid)
            edges.extend(out_edges)
        
        if (direction is None or direction == "in") and self.dg.in_edges:
            in_edges = self.dg.in_edges(self.identity.rid)
            edges.extend(in_edges)
        
        edge_rids = []
        for edge in edges:
            edge_data = self.dg.get_edge_data(*edge)
            if not edge_data: continue
            edge_rid = edge_data.get("rid")
            if not edge_rid: continue
            edge_rids.append(edge_rid)
       
        return edge_rids
    
    def get_neighbors(
        self,
        direction: Literal["in", "out"] | None = None,
        status: EdgeStatus | None = None,
        allowed_type: RIDType | None = None
    ) -> list[KoiNetNode]:
        """Returns neighboring nodes this node shares an edge with.

        All neighboring nodes returned by default, specify ``direction``
        to restrict to neighbors connected by incoming or outgoing edges
        only.
        """
        
        neighbors = set()
        for edge_rid in self.get_edges(direction):
            edge_bundle = self.cache.read(edge_rid)
            
            if not edge_bundle: 
                self.log.warning(f"Failed to find edge {edge_rid!r} in cache")
                continue
            
            edge_profile = edge_bundle.validate_contents(EdgeProfile)
                        
            if status and edge_profile.status != status:
                continue
            
            if allowed_type and allowed_type not in edge_profile.rid_types:
                continue
            
            if edge_profile.target == self.identity.rid:
                neighbors.add(edge_profile.source)
            elif edge_profile.source == self.identity.rid:
                neighbors.add(edge_profile.target)
            
        return list(neighbors)
