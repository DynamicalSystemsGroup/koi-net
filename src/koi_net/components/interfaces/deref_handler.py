from dataclasses import dataclass, field
from logging import Logger
from typing import TYPE_CHECKING

from rid_lib.core import RID, RIDType
from rid_lib.ext import Bundle

if TYPE_CHECKING:
    from ..effector import Effector


@dataclass
class DerefHandler:
    """Base class for dereference handler components.

    Derived classes MUST set the :attr:`.rid_types` to a tuple of acceptable
    types. The :meth:`.handle` method MUST be overriden, and may be passed any
    RID of the specified allowed RID types.

    .. note::
        If you only want to allow a single RID type, remember to add a
        trailing comma after so it is a valid tuple.

    Example::

        @dataclass
        class MyDerefHandler(DerefHandler):
            rid_types=(CustomType,)

            def handle(self, rid: CustomType):
                return
    """
    
    log: Logger
    effector: "Effector"
    
    rid_types: tuple[RIDType] = field(init=False)
    
    def __post_init__(self):
        self.effector.register_handler(self)
    
    def handle(self, rid: RID) -> Bundle | None:
        ...