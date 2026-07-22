from pydantic import BaseModel


class ServerConfig(BaseModel):
    """Server config for full nodes.

    The parameters in this class represent how a server should be hosted,
    not accessed. For example, a node may host a server at
    ``http://127.0.0.1:8000/koi-net``, but serve through nginx at
    ``https://example.com/koi-net``.
    """
    
    host: str = "127.0.0.1"
    port: int = 8000
    path: str | None = "/koi-net"
    
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{self.path or ''}"