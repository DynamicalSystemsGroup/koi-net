from dataclasses import dataclass
from functools import wraps
from logging import Logger

import httpx
from rid_lib import RID
from rid_lib.ext import Cache
from rid_lib.types import KoiNetNode
from pydantic import ValidationError

from .identity import NodeIdentity
from ..protocol.api.models import (
    RidsPayload,
    ManifestsPayload,
    BundlesPayload,
    EventsPayload,
    FetchRids,
    FetchManifests,
    FetchBundles,
    PollEvents,
    RequestModels,
    ResponseModels,
    ErrorResponse
)
from ..protocol.api.paths import (
    BROADCAST_EVENTS_PATH,
    POLL_EVENTS_PATH,
    FETCH_RIDS_PATH,
    FETCH_MANIFESTS_PATH,
    FETCH_BUNDLES_PATH
)
from ..protocol.errors import ErrorType
from ..protocol.node import NodeProfile, NodeType
from ..protocol.model_map import API_MODEL_MAP
from .secure_manager import SecureManager
from ..exceptions import (
    RemoteInvalidKeyError,
    RemoteInvalidSignatureError,
    RemoteInvalidTargetError,
    RequestError,
    SelfRequestError,
    PartialNodeQueryError,
    NodeNotFoundError,
    ServerError,
    TransportError,
    RemoteUnknownNodeError
)
from .error_handler import ErrorHandler


@dataclass
class RequestHandler:
    """Handles making requests to other KOI nodes."""
    
    log: Logger
    cache: Cache
    identity: NodeIdentity
    secure_manager: SecureManager
    error_handler: ErrorHandler
    
    def get_base_url(self, node_rid: KoiNetNode) -> str:
        """Retrieves URL of a node from its RID."""
        
        node_bundle = self.cache.read(node_rid)
        if node_bundle:
            node_profile = node_bundle.validate_contents(NodeProfile)
            if node_profile.node_type != NodeType.FULL:
                raise PartialNodeQueryError("Partial nodes don't have URLs")
            node_url = node_profile.base_url
        
        elif node_rid == self.identity.config.koi_net.first_contact.rid:
            node_url = self.identity.config.koi_net.first_contact.url
        
        else:
            raise NodeNotFoundError(f"URL not found for {node_rid!r}")
        
        self.log.debug(f"Resolved {node_rid!r} to {node_url}")
        return node_url
    
    @staticmethod
    def report_exception(func):
        """Logs request errors as warnings."""
        @wraps(func)
        def wrapper(self: "RequestHandler", *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except RequestError as err:
                self.log.warning(err)
                raise
        return wrapper
    
    @report_exception
    def make_request(
        self,
        node: KoiNetNode,
        path: str, 
        request: RequestModels,
    ) -> ResponseModels | None:
        """Makes a request to a node.
        
        Wraps request object in a signed envelope, and validates the
        signed envelope it receives in response before returning the
        unwrapped response model.
        
        Catches HTTP and protocol errors, and handles or reraises them.
        """
        
        if node == self.identity.rid:
            raise SelfRequestError("Don't talk to yourself")
        
        url = self.get_base_url(node) + path
        self.log.info(f"Making request to {url}")
    
        signed_envelope = self.secure_manager.create_envelope(
            payload=request,
            target=node
        )
        
        data = signed_envelope.model_dump_json(exclude_none=True)
        
        try:
            result = httpx.post(
                url=url, 
                content=data, 
                headers={"Content-Type": "application/json"})
            result.raise_for_status()
            self.error_handler.reset_timeout_counter(node)
            
        except httpx.RequestError as e:
            self.log.debug("Failed to connect")
            self.error_handler.handle_connection_error(node)
            raise TransportError(e)
        
        except httpx.HTTPStatusError:
            """Possible errors:
            
            4xx - KOI-net protocol error, validate body
            404/405 - not implementing endpoints, or misconfigured URL
            
            500 - internal server error
            """
            try:
                resp = ErrorResponse.model_validate_json(result.text)
                self.error_handler.handle_protocol_error(resp.error, node)
                
                match resp.error:
                    case ErrorType.UnknownNode:
                        raise RemoteUnknownNodeError(f"Peer couldn't resolve this node's RID")
                    case ErrorType.InvalidKey:
                        raise RemoteInvalidKeyError(f"Peer marked this node's public key as invalid")
                    case ErrorType.InvalidSignature:
                        raise RemoteInvalidSignatureError("Peer marked envelope signature as invalid")
                    case ErrorType.InvalidTarget:
                        raise RemoteInvalidTargetError("Envelope target is not the peer node")
            
            except ValidationError as e:
                raise ServerError(e)
            
        
        resp_env_model = API_MODEL_MAP[path].response_envelope
        if not resp_env_model:
            return
        
        try:
            resp_envelope = resp_env_model.model_validate_json(result.text)
        except ValidationError as e:
            raise ServerError(e)
        
        self.secure_manager.validate_envelope(resp_envelope)
        
        return resp_envelope.payload
    
    def broadcast_events(
        self, 
        node: RID, 
        req: EventsPayload | None = None,
        **kwargs
    ) -> None:
        """Broadcasts events to a node.

        Pass an :class:`~koi_net.protocol.api.models.EventsPayload` object as
        ``req``, or its fields as kwargs.
        """
        request = req or EventsPayload.model_validate(kwargs)
        self.make_request(node, BROADCAST_EVENTS_PATH, request)
        self.log.info(f"Broadcasted {len(request.events)} event(s) to {node!r}")
        
    def poll_events(
        self, 
        node: RID, 
        req: PollEvents | None = None,
        **kwargs
    ) -> EventsPayload:
        """Polls events from a node.

        Pass a :class:`~koi_net.protocol.api.models.PollEvents` object as
        ``req`` or fields as kwargs.
        """
        request = req or PollEvents.model_validate(kwargs)
        resp = self.make_request(node, POLL_EVENTS_PATH, request)
        self.log.info(f"Polled {len(resp.events)} events from {node!r}")
        return resp
        
    def fetch_rids(
        self, 
        node: RID, 
        req: FetchRids | None = None,
        **kwargs
    ) -> RidsPayload:
        """Fetches RIDs from a node.

        Pass a :class:`~koi_net.protocol.api.models.FetchRids` object as
        ``req`` or fields as kwargs.
        """
        request = req or FetchRids.model_validate(kwargs)
        resp = self.make_request(node, FETCH_RIDS_PATH, request)
        self.log.info(f"Fetched {len(resp.rids)} RID(s) from {node!r}")
        return resp
                
    def fetch_manifests(
        self, 
        node: RID, 
        req: FetchManifests | None = None,
        **kwargs
    ) -> ManifestsPayload:
        """Fetches manifests from a node.

        Pass a :class:`~koi_net.protocol.api.models.FetchManifests` object as
        ``req`` or fields as kwargs.
        """
        request = req or FetchManifests.model_validate(kwargs)
        resp = self.make_request(node, FETCH_MANIFESTS_PATH, request)
        self.log.info(f"Fetched {len(resp.manifests)} manifest(s) from {node!r}")
        return resp
                
    def fetch_bundles(
        self, 
        node: RID, 
        req: FetchBundles | None = None,
        **kwargs
    ) -> BundlesPayload:
        """Fetches bundles from a node.

        Pass a :class:`~koi_net.protocol.api.models.FetchBundles` object as
        ``req`` or fields as kwargs.
        """
        request = req or FetchBundles.model_validate(kwargs)
        resp = self.make_request(node, FETCH_BUNDLES_PATH, request)
        self.log.info(f"Fetched {len(resp.bundles)} bundle(s) from {node!r}")
        return resp