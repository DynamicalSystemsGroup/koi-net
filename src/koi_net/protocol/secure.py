from rid_lib.types import KoiNetNode
import structlog
from base64 import b64decode, b64encode
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from rid_lib.ext.utils import sha256_hash
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature, 
    encode_dss_signature
)

log = structlog.stdlib.get_logger()


def der_to_raw_signature(der_signature: bytes, curve=ec.SECP256R1()) -> bytes:
    """Converts a DER-encoded signature to raw r||s format."""
    
    # Decode the DER signature to get r and s
    r, s = decode_dss_signature(der_signature)
    
    # Determine byte length based on curve bit size
    byte_length = (curve.key_size + 7) // 8
    
    # Convert r and s to big-endian byte arrays of fixed length
    r_bytes = r.to_bytes(byte_length, byteorder='big')
    s_bytes = s.to_bytes(byte_length, byteorder='big')
    
    # Concatenate r and s
    return r_bytes + s_bytes


def raw_to_der_signature(raw_signature: bytes, curve=ec.SECP256R1()) -> bytes:
    """Converts a raw r||s signature to DER format."""
    
    # Determine byte length based on curve bit size
    byte_length = (curve.key_size + 7) // 8
    
    # Split the raw signature into r and s components
    if len(raw_signature) != 2 * byte_length:
        raise ValueError(f"Raw signature must be {2 * byte_length} bytes for {curve.name}")
    
    r_bytes = raw_signature[:byte_length]
    s_bytes = raw_signature[byte_length:]
    
    # Convert bytes to integers
    r = int.from_bytes(r_bytes, byteorder='big')
    s = int.from_bytes(s_bytes, byteorder='big')
    
    # Encode as DER
    return encode_dss_signature(r, s)


class PrivateKey:
    priv_key: ec.EllipticCurvePrivateKey
    
    def __init__(self, priv_key):
        self.priv_key = priv_key
    
    @classmethod
    def generate(cls):
        """Generates a new :class:`.PrivateKey`."""
        return cls(priv_key=ec.generate_private_key(ec.SECP256R1()))

    def public_key(self) -> "PublicKey":
        """Returns instance of :class:`.PublicKey` derived from this private key."""
        return PublicKey(self.priv_key.public_key())
    
    @classmethod
    def from_pem(cls, priv_key_pem: str, password: str):
        """Loads :class:`.PrivateKey` from encrypted PEM string."""
        return cls(
            priv_key=serialization.load_pem_private_key(
                data=priv_key_pem.encode(),
                password=password.encode()
            )
        )

    def to_pem(self, password: str) -> str:
        """Saves :class:`.PrivateKey` to encrypted PEM string."""
        return self.priv_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
        ).decode()
        
    def sign(self, message: bytes) -> str:
        """Returns base64 encoded raw signature bytes of the form r||s."""
        hashed_message = sha256_hash(message.decode())
        
        der_signature_bytes = self.priv_key.sign(
            data=message,
            signature_algorithm=ec.ECDSA(hashes.SHA256())
        )
        
        raw_signature_bytes = der_to_raw_signature(der_signature_bytes)
        
        signature = b64encode(raw_signature_bytes).decode()
        
        log.debug(f"Signing message with [{self.public_key().to_der()}]")
        log.debug(f"hash: {hashed_message}")
        log.debug(f"signature: {signature}")
        
        return signature


class PublicKey:
    pub_key: ec.EllipticCurvePublicKey
    
    def __init__(self, pub_key):
        self.pub_key = pub_key
    
    @classmethod
    def from_pem(cls, pub_key_pem: str):
        """Loads :class:`.PublicKey` from PEM string."""
        return cls(
            pub_key=serialization.load_pem_public_key(
                data=pub_key_pem.encode()
            )
        )
        
    def to_pem(self) -> str:
        """Saves :class:`.PublicKey` to PEM string."""
        return self.pub_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        
    @classmethod
    def from_der(cls, pub_key_der: str):
        """Loads :class:`.PublicKey` from base64 encoded DER string."""
        return cls(
            pub_key=serialization.load_der_public_key(
                data=b64decode(pub_key_der)
            )
        )
    
    def to_der(self) -> str:
        """Saves :class:`.PublicKey` to base64 encoded DER string."""
        return b64encode(
            self.pub_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        ).decode()
        
    def to_node_rid(self, name) -> KoiNetNode:
        """Returns an orn:koi-net.node RID from hashed DER string."""
        return KoiNetNode(
            name=name,
            hash=sha256_hash(self.to_der())
        )
        
    def verify(self, signature: str, message: bytes):
        """Verifies a signature for a message.

        :raises cryptography.exceptions.InvalidSignature: if verification fails
        """
        
        raw_signature_bytes = b64decode(signature)
        der_signature_bytes = raw_to_der_signature(raw_signature_bytes)
        
        self.pub_key.verify(
            signature=der_signature_bytes,
            data=message,
            signature_algorithm=ec.ECDSA(hashes.SHA256())
        )
