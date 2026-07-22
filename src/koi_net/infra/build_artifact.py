import inspect
from collections import deque
from typing import TYPE_CHECKING, Any

import structlog

from ..exceptions import BuildError
from .consts import (
    COMPONENT_TYPE_FIELD,
    DEPENDS_ON_FIELD, 
    START_FUNC_NAME, 
    STOP_FUNC_NAME
)
from .component import CompType

if TYPE_CHECKING:
    from .assembler import Assembler

log = structlog.stdlib.get_logger()


class BuildArtifact:
    """Used by the :class:`~koi_net.infra.assembler.Assembler` to determine
    the initialization, start and stop order of components using a graph
    solver.
    """
    
    assembler: "Assembler"
    
    comp_dict: dict[str, Any]
    comp_types: dict[str, CompType]
    init_graph: dict[str, set[str]]
    start_graph: dict[str, set[str]]
    stop_graph: dict[str, set[str]]
    
    init_order: list[str]
    start_order: list[str]
    stop_order: list[str]
    
    def __init__(self, assembler: "Assembler"):
        self.assembler = assembler
        
    def collect_components(self):
        """Collects components from the assembler's class variable definitions."""
        
        self.comp_dict = {}
        # adds components from class and all base classes. skips `type`, and runs in reverse so that sub classes override super class values
        for base in reversed(inspect.getmro(self.assembler)[:-1]):
            for k, v in vars(base).items():
                # excludes built in, private, and `None` attributes
                if k.startswith("_") or v is None:
                    continue
                
                self.comp_dict[k] = v
        log.debug(f"Collected {len(self.comp_dict)} components")
    
    def build_init_graph(self):
        """Builds initialization dependency graph and component type map.
        Results stored in :attr:`.init_graph` and :attr:`.comp_types`.
        
        Graph representation is an adjacency list: the key is a component 
        name, and the value is a tuple containing names of the depedencies.
        """
        
        self.comp_types = {}
        self.init_graph = {}
        
        for comp_name, comp in self.comp_dict.items():
            init_dependencies = []
            
            explict_type = getattr(comp, COMPONENT_TYPE_FIELD, None)
            if explict_type:
                self.comp_types[comp_name] = explict_type
                
            elif not callable(comp):
                # non callable components are objects treated "as is"
                self.comp_types[comp_name] = CompType.OBJECT
            else:
                # callable components default to singletons
                self.comp_types[comp_name] = CompType.SINGLETON
            
            if self.comp_types[comp_name] == CompType.SINGLETON:
                sig = inspect.signature(comp)
                init_dependencies = set(sig.parameters)
                
                # difference of sets: dependencies and component names
                # non empty set indicates invalid dependency
                invalid_init_deps = init_dependencies - set(self.comp_dict)
                if invalid_init_deps:
                    log.warning(f"Ignoring undefined init dependencies {invalid_init_deps} on component '{comp_name}'")
                    init_dependencies -= invalid_init_deps
                    
            self.init_graph[comp_name] = init_dependencies
        
        log.debug("Built init dependency graph")
                
    def build_start_graph(self):
        """Builds start dependency graph, results stored in :attr:`.start_graph`."""
        
        self.start_graph = {}
        start_components = {
            name for name, comp in self.comp_dict.items()
            if getattr(comp, START_FUNC_NAME, None)
        }
        for comp_name, comp in self.comp_dict.items():
            if self.comp_types[comp_name] != CompType.SINGLETON:
                continue
            
            if comp_name not in start_components:
                continue
            
            start_func = getattr(comp, START_FUNC_NAME)
            start_dependencies = getattr(start_func, DEPENDS_ON_FIELD, set())
            invalid_start_deps = start_dependencies - start_components
            # ignores dependencies without a start method
            if invalid_start_deps:
                log.warning(f"Ignoring undefined start dependencies {invalid_start_deps} on component '{comp_name}'")
                start_dependencies -= invalid_start_deps
                
            self.start_graph[comp_name] = start_dependencies
        
        log.debug("Built start dependency graph")
        
    def build_stop_graph(self):
        """Builds stop dependency graph, results stored in :attr:`.stop_graph`."""
        
        self.stop_graph = {}
        
        stop_components = {
            name for name, comp in self.comp_dict.items()
            if getattr(comp, STOP_FUNC_NAME, None)
        }
        
        reverse_start_graph = self.reverse_adj_list(self.start_graph)
        for comp_name, comp in self.comp_dict.items():
            if self.comp_types[comp_name] != CompType.SINGLETON:
                continue
            
            if comp_name not in stop_components:
                continue
            
            # looks for dependencies in this order:
            # @depends_on decorator -> reverse start graph -> empty set
            stop_func = getattr(comp, STOP_FUNC_NAME)
            stop_dependencies = getattr(
                stop_func,
                DEPENDS_ON_FIELD, 
                # default:
                reverse_start_graph.get(
                    comp_name, 
                    # default:
                    set()
                )
            )
            
            invalid_stop_deps = stop_dependencies - stop_components
            # ignores dependencies without a stop method
            if invalid_stop_deps:
                log.warning(f"Ignoring undefined stop dependencies {invalid_stop_deps} on component '{comp_name}'")
                stop_dependencies -= invalid_stop_deps
                
            self.stop_graph[comp_name] = stop_dependencies
        
        log.debug("Built stop dependency graph")
        
    @staticmethod
    def reverse_adj_list(adj: dict[str, set[str]]):
        r_adj: dict[str, set[str]] = {}
        for node in adj:
            r_adj.setdefault(node, set())
            for n in adj[node]:
                r_adj.setdefault(n, set())
                r_adj[n].add(node)
        return r_adj
    
    @staticmethod
    def topo_sort(adj: dict[str, set[str]]):
        """Topological sort of directed graph using Kahn's algorithm."""
        
        # reverse adj list: n -> incoming neighbors
        r_adj = BuildArtifact.reverse_adj_list(adj)
        
        # how many outgoing edges each node has
        out_degree = {
            n: len(neighbors) 
            for n, neighbors in adj.items()
        }
        
        # initializing queue: nodes w/o dependencies
        queue = deque()
        for node in out_degree:
            if out_degree[node] == 0:
                queue.append(node)
        
        ordering = []
        while queue:
            # removes node from graph
            n = queue.popleft()
            ordering.append(n)
            
            # updates out degree for nodes dependent on this node
            for next_n in r_adj[n]:
                out_degree[next_n] -= 1
                # adds nodes now without dependencies to queue
                if out_degree[next_n] == 0:
                    queue.append(next_n)
        
        if len(ordering) != len(adj):
            cycle_nodes = set(adj) - set(ordering)
            raise BuildError(f"Found cycle in dependency graph, the following nodes could not be ordered: {cycle_nodes}")
        
        return ordering
    
    def build_stop_order(self, start_order: list[str]) -> list[str]:
        """Builds component stop order.

        Reverse of start order, only including components with a stop method.

        .. note::
            Components defining a stop method MUST also define a start method.
        """
        
        stop_order = []
        for comp_name in reversed(start_order):
            comp = self.comp_dict[comp_name]
            if getattr(comp, STOP_FUNC_NAME, None):
                stop_order.append(comp_name)
        
        return stop_order

    @staticmethod
    def visualize(adj: dict[str, list[str]]) -> str:
        """Returns representation of dependency graph in Graphviz DOT language."""
        
        s = "digraph G {\n"
        for node, neighbors in adj.items():
            if node == "graph":
                node = "graph_"
            
            s += f"\t{node};\n"
            for n in neighbors:
                if n == "graph":
                    n = "graph_"
                
                s += f"\t{node} -> {n};\n"
        s += "}"
        return s
    
    def build(self):
        """Builds artifact, populates orderings."""
        
        log.debug("Creating build artifact...")
        self.collect_components()
        
        self.build_init_graph()
        log.debug("Starting init graph topo sort...")
        self.init_order = self.topo_sort(self.init_graph)
        log.debug("Init order: " + " -> ".join(self.init_order))
        
        self.build_start_graph()
        log.debug("Starting start graph topo sort...")
        self.start_order = self.topo_sort(self.start_graph)
        log.debug("Start order: " + " -> ".join(self.start_order))
        
        self.build_stop_graph()
        log.debug("Starting stop graph topo sort...")
        self.stop_order = self.topo_sort(self.stop_graph)
        log.debug("Stop order: " + " -> ".join(self.stop_order))
        log.debug("Done")
