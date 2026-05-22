from dataclasses import dataclass, field
from logging import Logger
from enum import StrEnum
from typing import TYPE_CHECKING

from rid_lib.ext import Cache, Bundle
from rid_lib.core import RID
from rid_lib.types import KoiNetNode

from .resolver import NetworkResolver
from .kobj_queue import KobjQueue

if TYPE_CHECKING:
    from .interfaces import DerefHandler


class BundleSource(StrEnum):
    CACHE = "CACHE"
    ACTION = "ACTION"

@dataclass
class Effector:
    """Subsystem for dereferencing RIDs."""
    
    log: Logger
    cache: Cache
    resolver: NetworkResolver
    kobj_queue: KobjQueue
    
    deref_handlers: list["DerefHandler"] = field(init=False, default_factory=list)
    
    def register_handler(self, handler: "DerefHandler"):
        self.deref_handlers.append(handler)
        self.log.info(f"Registered deref handler {handler.__class__.__name__}")
    
    def _try_cache(self, rid: RID) -> tuple[Bundle, BundleSource] | None:
        bundle = self.cache.read(rid)
        
        if bundle:
            self.log.debug("Cache hit")
            return bundle, BundleSource.CACHE
        else:
            self.log.debug("Cache miss")
            return None
            
    def _try_handler(self, rid: RID) -> tuple[Bundle, BundleSource] | None:
        handler = next(
            (h for h in self.deref_handlers if type(rid) in h.rid_types), 
            None
        )
        
        if not handler:
            self.log.debug("No handler found")
            return None
        
        bundle = handler.handle(rid)
        
        if bundle:
            self.log.debug("Handler hit")
            return bundle, BundleSource.ACTION
        else:
            self.log.debug("Handler miss")
            return None
        
    def _try_network(self, rid: RID) -> tuple[Bundle, KoiNetNode] | None:
        bundle, source = self.resolver.fetch_remote_bundle(rid)
        
        if bundle:
            self.log.debug("Network hit")
            return bundle, source
        else:
            self.log.debug("Network miss")
            return None
        
    def deref(
        self, 
        rid: RID,
        refresh_cache: bool = False,
        use_network: bool = False,
        handle_result: bool = True,
        write_through: bool = False
    ) -> Bundle | None:
        """Dereferences an RID.
        
        Attempts to dereference an RID by (in order) reading the cache, 
        calling a bound action, or fetching from other nodes in the 
        newtork.
        
        Args:
            rid: RID to dereference
            refresh_cache: skips cache read when `True` 
            use_network: enables fetching from other nodes when `True`
            handle_result: sends resulting bundle to kobj queue when `True`
            write_through: waits for kobj queue to empty when `True`
        """
        
        self.log.debug(f"Dereferencing {rid!r}")
        
        bundle, source = (
            # if `refresh_cache`, skip try cache
            not refresh_cache and self._try_cache(rid) or 
            self._try_handler(rid) or
            use_network and self._try_network(rid) or
            # if not found, bundle and source set to None
            (None, None) 
        )
        
        if (
            handle_result 
            and bundle is not None 
            and source != BundleSource.CACHE
        ):            
            self.kobj_queue.push(
                bundle=bundle, 
                source=source if type(source) is KoiNetNode else None
            )
            
            if write_through:
                self.kobj_queue.wait()
                
        return bundle