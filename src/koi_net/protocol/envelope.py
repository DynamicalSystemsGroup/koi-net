import structlog
from typing import Generic, TypeVar
from pydantic import BaseModel
from rid_lib.types import KoiNetNode

from .secure import PrivateKey, PublicKey
from .api.models import RequestModels, ResponseModels

log = structlog.stdlib.get_logger()


T = TypeVar("T", bound=RequestModels | ResponseModels)

class SignedEnvelope(BaseModel, Generic[T]):
    payload: T
    source_node: KoiNetNode
    target_node: KoiNetNode
    signature: str
    
    def verify_with(self, pub_key: PublicKey):
        """Verifies signed envelope with public key.
        
        Raises `cryptography.exceptions.InvalidSignature` on failure.
        """
        
        # IMPORTANT: calling `model_dump()` loses all typing! when converting between SignedEnvelope and UnsignedEnvelope, use the Pydantic classes, not the dictionary form
        
        unsigned_envelope = UnsignedEnvelope[T](
            payload=self.payload,
            source_node=self.source_node,
            target_node=self.target_node 
        )
        
        serialized_signed_envelope = unsigned_envelope.model_dump_json(
            exclude_none=True)
        
        log.debug(f"Verifying envelope: {serialized_signed_envelope}")

        pub_key.verify(
            signature=self.signature,
            message=serialized_signed_envelope.encode()
        )

class UnsignedEnvelope(BaseModel, Generic[T]):
    payload: T
    source_node: KoiNetNode
    target_node: KoiNetNode
    
    def sign_with(self, priv_key: PrivateKey) -> SignedEnvelope[T]:
        """Signs with private key and returns `SignedEnvelope`."""
        
        serialized_unsigned_envelope = self.model_dump_json(
            exclude_none=True)
        
        log.debug(f"Signing envelope: {serialized_unsigned_envelope}")
        log.debug(f"Type: [{type(self.payload)}]")
        
        signature = priv_key.sign(
            message=serialized_unsigned_envelope.encode()
        )
        
        return SignedEnvelope(
            payload=self.payload,
            source_node=self.source_node,
            target_node=self.target_node,
            signature=signature
        )
