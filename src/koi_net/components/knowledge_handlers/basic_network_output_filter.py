from dataclasses import dataclass

from rid_lib.types import KoiNetEdge, KoiNetNode

from koi_net.protocol.edge import EdgeProfile
from koi_net.protocol.knowledge_object import KnowledgeObject
from ..interfaces import KnowledgeHandler, HandlerType
from ..identity import NodeIdentity
from ..graph import NetworkGraph


@dataclass
class BasicNetworkOutputFilter(KnowledgeHandler):
    """Sets network targets of outgoing event for knowledge object.
            
    Allows broadcasting of all RID types this node is an event provider 
    for (set in node profile), and other nodes have subscribed to. All 
    nodes will also broadcast events about their own (internally sourced) 
    KOI node, and KOI edges that they are part of, regardless of their 
    node profile configuration. Finally, nodes will also broadcast about 
    edges to the other node involved (regardless of if they are subscribed).
    """
    
    identity: NodeIdentity
    graph: NetworkGraph
    
    handler_type = HandlerType.Network
    
    def handle(self, kobj: KnowledgeObject):
        involves_this_node = False
        # internally source knowledge objects
        if kobj.source is None:
            if type(kobj.rid) is KoiNetNode:
                if (kobj.rid == self.identity.rid):
                    involves_this_node = True
            
            elif type(kobj.rid) is KoiNetEdge:
                edge_profile = kobj.bundle.validate_contents(EdgeProfile)
                
                if edge_profile.source == self.identity.rid:
                    self.log.debug(f"Adding edge target '{edge_profile.target!r}' to network targets")
                    kobj.network_targets.add(edge_profile.target)
                    involves_this_node = True
                    
                elif edge_profile.target == self.identity.rid:
                    self.log.debug(f"Adding edge source '{edge_profile.source!r}' to network targets")
                    kobj.network_targets.add(edge_profile.source)
                    involves_this_node = True
        
        if (type(kobj.rid) in self.identity.profile.provides.event or involves_this_node):
            subscribers = self.graph.get_neighbors(
                direction="out",
                allowed_type=type(kobj.rid)
            )
            
            self.log.debug(f"Updating network targets with '{type(kobj.rid)}' subscribers: {subscribers}")
            kobj.network_targets.update(subscribers)
            
        if kobj.source and kobj.source in kobj.network_targets:
            kobj.network_targets.remove(kobj.source)
            self.log.debug(f"Removed event source '{kobj.source}' from network targest")
            
        return kobj