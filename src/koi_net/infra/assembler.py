from typing import Any, Self

import structlog

from ..exceptions import BuildError
from .build_artifact import BuildArtifact, CompType
from .container import NodeContainer

log = structlog.stdlib.get_logger()


class Assembler:
    """Assembles components into a container. The "blueprint" of the
    dependency injection system, derived classes define components
    as class variables.

    Initializing this class will return a
    :class:`~koi_net.infra.container.NodeContainer`, which can be
    overriden by setting the ``_container`` class variable.
    """
    
    _container: type[NodeContainer] = NodeContainer
    
    # annotation hack to show the components and container methods
    # component types will derive from the assembly (appearing to be a 
    # class instead of an instance), and the node container will expose
    # lifecycle methods.
    def __new__(cls, *args, **kwargs) -> Self | NodeContainer:
        """Returns assembled node container."""
        
        log.debug(f"Assembling '{cls.__name__}'")
        
        artifact = BuildArtifact(cls)
        artifact.build()
        
        components = cls._build_components(artifact)
        
        log.debug("Returning assembled node")
        # returns container populated with components, build artifact,
        # and any kwargs passed into this constructor
        return cls._container(
            artifact=artifact,
            components=components,
            **kwargs
        )
    
    @staticmethod
    def _build_components(artifact: BuildArtifact):
        """Initializes components according to the
        :class:`~koi_net.infra.build_artifact.BuildArtifact`'s
        :attr:`~koi_net.infra.build_artifact.BuildArtifact.init_order`,
        and returns them as a dict, where the key is the component name.
        """
        
        log.debug("Building components...")
        components: dict[str, Any] = {}
        for comp_name in artifact.init_order:
        # for comp_name, (comp_type, dep_names) in dep_graph.items():
            comp = artifact.comp_dict[comp_name]
            comp_type = artifact.comp_types[comp_name]
            
            if comp_type == CompType.OBJECT:
                components[comp_name] = comp
            
            elif comp_type == CompType.SINGLETON:
                # builds depedency dict for current component
                dependencies = {}
                for dep in artifact.init_graph[comp_name]:
                    if dep not in components:
                        raise BuildError(f"Couldn't find required component '{dep}'")
                    dependencies[dep] = components[dep]
                components[comp_name] = comp(**dependencies)
        log.debug("Done")
        
        return components
