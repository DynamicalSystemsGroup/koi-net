from pydantic import BaseModel, Field

from ..infra import provides, CompType
from .env_config import EnvConfig
from .koi_net_config import KoiNetConfig


@provides(CompType.OBJECT)
class BaseNodeConfig(BaseModel):
    """Base node config class, intended to be extended.
    
    Using the `comp_type.object` decorator to mark this class as an
    object to be treated "as is" rather than attempting to initialize it
    during the build.
    """
    
    koi_net: KoiNetConfig
    # NOTE: EnvConfig has to use a default factory, otherwise it will be
    # evaluated during the library import and cause an error if any
    # env variables are undefined
    env: EnvConfig = Field(default_factory=EnvConfig)
    
    # typing passthrough for config provider component
    def save_to_yaml(self) -> None: ...