"""Defines decorators for manipulating component metadata, informing the 
assembly process.
"""

from enum import StrEnum

from .consts import COMPONENT_TYPE_FIELD, DEPENDS_ON_FIELD


class CompType(StrEnum):
    """Defines component types.
    
    Singletons are callable components (typically classes) which need to
    be instantiated prior to use. They define their dependencies in their 
    function signature (this is `__init__` for classes).
    
    Objects are constant components that are simply passed "as is."
    """
    SINGLETON = "SINGLETON"
    OBJECT = "OBJECT"
    
def provides(component_type: CompType):
    """Decorator for a component that overrides its type.
    
    This is typically used to pass a class "as is." Example:

    .. code-block:: python

        from koi_net.infra import provides, CompType

        @provides(CompType.OBJECT)
        class MyClassComponent:
            ...
    """
    def decorator(obj):
        setattr(obj, COMPONENT_TYPE_FIELD, component_type)
        return obj
    return decorator

def depends_on(*components):
    """Decorator that declares the dependencies of a start or stop method
    in a component class.
    
    Example:

    .. code-block:: python

        from koi_net.infra import depends_on

        class MyComponent:
            @depends_on("another_component")
            def start(self):
                ...
    """
    def decorator(obj):
        setattr(obj, DEPENDS_ON_FIELD, set(components))
        return obj
    return decorator