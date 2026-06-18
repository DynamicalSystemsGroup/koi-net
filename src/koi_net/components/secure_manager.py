from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path

import cryptography.exceptions
from rid_lib.ext import Bundle, Cache
from rid_lib.ext.utils import sha256_hash
from rid_lib.types import KoiNetNode

from .config_provider import ConfigProvider
from .identity import NodeIdentity
from ..protocol.envelope import UnsignedEnvelope, SignedEnvelope
from ..protocol.secure import PublicKey
from ..protocol.api.models import ApiModels, EventsPayload
from ..protocol.event import EventType
from ..protocol.node import NodeProfile
from ..protocol.secure import PrivateKey
from ..exceptions import (
    UnknownNodeError,
    InvalidKeyError,
    InvalidSignatureError,
    InvalidTargetError
)
from ..config.base import BaseNodeConfig


@dataclass
class SecureManager:
    """Subsystem handling secure protocol logic."""
    
    log: Logger
    identity: NodeIdentity
    cache: Cache
    config: ConfigProvider | BaseNodeConfig
    root_dir: Path
    
    priv_key: PrivateKey = field(init=False)
    
    def __post_init__(self):
        self.load_priv_key()
        
    @property
    def pem_path(self) -> Path:
        return self.root_dir / self.config.koi_net.private_key_pem_path
    
    def create_priv_key(self):
        self.priv_key = PrivateKey.generate()
        
        with open(self.pem_path, "w") as f:
            f.write(self.priv_key.to_pem(self.config.env.priv_key_password))
        self.log.debug("Generated new private key, no PEM file found")
        
        pub_key = self.priv_key.public_key()
        self.config.koi_net.node_rid = pub_key.to_node_rid(
            name=self.config.koi_net.node_name)
        
        if self.config.koi_net.node_profile.public_key != pub_key.to_der():
            if self.config.koi_net.node_profile.public_key:
                self.log.warning("New private key overwriting old public key!")
            
            self.config.koi_net.node_profile.public_key = pub_key.to_der()
        self.config.save_to_yaml()
    
    def load_priv_key(self):
        """Loads private key from PEM file path in config."""
        
        try:
            with open(self.pem_path, "r") as f:
                priv_key_pem = f.read()
                
                self.priv_key = PrivateKey.from_pem(
                    priv_key_pem=priv_key_pem,
                    password=self.config.env.priv_key_password
                )
        except FileNotFoundError:
            self.create_priv_key()
        
        except ValueError:
            self.log.error("Incorrect password, could not decrypt PEM")
            # TODO: figure out more graceful way of failing startup sequence
            raise
        
    def handle_unknown_node(self, envelope: SignedEnvelope) -> Bundle | None:
        """Attempts to find node profile in provided envelope.
        
        If an unknown node sends an envelope, it may still be able to be
        validated if that envelope contains their node profile. This is
        essential for allowing unknown nodes to handshake and introduce
        themselves. Only an `EventsPayload` contain a `NEW` event for a 
        node profile for the source node is permissible.
        """
        if type(envelope.payload) != EventsPayload:
            return None
            
        for event in envelope.payload.events:
            # must be NEW event for bundle of source node's profile
            if event.rid != envelope.source_node:
                continue
            if event.event_type != EventType.NEW:
                continue
            
            return event.bundle
        return None
        
    def create_envelope(
        self, payload: ApiModels, target: KoiNetNode
    ) -> SignedEnvelope:
        """Returns signed envelope to target from provided payload."""
        return UnsignedEnvelope(
            payload=payload,
            source_node=self.identity.rid,
            target_node=target
        ).sign_with(self.priv_key)
        
    def validate_envelope(self, envelope: SignedEnvelope):
        """Validates signed envelope from another node."""
        
        node_bundle = (
            self.cache.read(envelope.source_node) or
            self.handle_unknown_node(envelope)
        )
        
        if not node_bundle:
            raise UnknownNodeError(f"Couldn't resolve {envelope.source_node}")
        
        node_profile = node_bundle.validate_contents(NodeProfile)
        
        # check that public key matches source node RID
        if envelope.source_node.hash != sha256_hash(node_profile.public_key):
            raise InvalidKeyError("Invalid public key on new node!")
        
        # check envelope signed by validated public key
        pub_key = PublicKey.from_der(node_profile.public_key)
        try:
            envelope.verify_with(pub_key)
        except cryptography.exceptions.InvalidSignature:
            raise InvalidSignatureError(f"Signature {envelope.signature} is invalid.")
        
        # check that this node is the target of the envelope
        if envelope.target_node != self.identity.rid:
            raise InvalidTargetError(f"Envelope target {envelope.target_node!r} is not me")

