import socket
from dataclasses import dataclass
from logging import Logger

from ..infra import depends_on
from ..config.full_node import FullNodeConfig
from .config_provider import ConfigProvider


@dataclass
class PortManager:
    """Acquires a port for the :class:`~koi_net.components.server.NodeServer`,
    looks for free ports if specified one already in use."""
    
    log: Logger
    config: ConfigProvider | FullNodeConfig
    
    @depends_on("config")
    def start(self):
        self.acquire_port()
        
    def acquire_port(self):
        """Attempts to acquire server port defined in config, increments
        port number if port in use until an open one is found. Config is
        then updated if new port acquired.
        """
        
        base_url_is_derived = (self.config.koi_net.node_profile.base_url == self.config.server.url)
        
        changed_port: bool = False
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((self.config.server.host, self.config.server.port)) != 0:
                    break
                
                self.log.debug(f"Port {self.config.server.port} in use")
                self.config.server.port += 1
                changed_port = True
        
        self.log.debug(f"Acquired port {self.config.server.port}")
        
        if base_url_is_derived and changed_port:
            self.log.debug("Updating node profile")
            self.config.koi_net.node_profile.base_url = self.config.server.url
        
        self.config.save_to_yaml()