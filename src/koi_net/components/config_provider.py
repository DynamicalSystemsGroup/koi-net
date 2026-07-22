import inspect
import os
from pathlib import Path
from contextlib import contextmanager

from pydantic import ValidationError

from ..exceptions import MissingEnvVarsError
from ..config import EnvConfig
from ..config.base import BaseNodeConfig


DELEGATE = "_delegate"

class ConfigProvider:
    """Loads node config from a YAML file, and provides proxied access to it."""
    
    _file_path: str = "config.yaml"
    _file_content: str
    
    _schema: type[BaseNodeConfig]
    _root_dir: Path
    
    # the delegate is the pydantic config class which access is proxied to
    _delegate: BaseNodeConfig
    
    def __init__(self, config_schema, root_dir):
        object.__setattr__(self, "_schema", config_schema)
        object.__setattr__(self, "_root_dir", root_dir)
        
        # this is a special case to allow config state dependent components
        # to initialize without a "lazy initialization" approach, in general
        # components SHOULD NOT execute code in their init phase
        
        self._validate_env_vars()
        self._load_from_yaml()
        
    def _set_delegate(self, delegate: BaseNodeConfig):
        object.__setattr__(self, DELEGATE, delegate)
        
    def _get_delegate(self) -> BaseNodeConfig:
        return object.__getattribute__(self, DELEGATE)
    
    def __getattr__(self, name):
        return getattr(self._get_delegate(), name)
    
    def __setattr__(self, name, value):
        """Overrides set attribute for ALL members of this class.

        Any non proxying set attribute call needs to be done using
        ``object.__attribute__(self, name)``.
        """
        
        delegate = self._get_delegate()
        setattr(delegate, name, value)

    def _validate_env_vars(self):
        """Validates environment variables and raises formatted exception.
        
        Useful for interfacing with CLI, catch exception and print the 
        missing vars to the screen.
        """
        
        for field in self._schema.model_fields.values():
            field_type = field.annotation
            if inspect.isclass(field_type) and issubclass(field_type, EnvConfig):
                try:
                    field_type()
                except ValidationError as exc:
                    missing_vars = [
                        err["loc"][0].upper()
                        for err in exc.errors()
                        if err["type"] == "missing"
                    ]
                    raise MissingEnvVarsError(
                        f"Missing required vars: {','.join(v for v in missing_vars)}",
                        vars=missing_vars)
    
    def _load_from_yaml(self):
        """Loads config from YAML file, or generates it if missing."""
        
        from ruamel.yaml import YAML
        yaml = YAML()
        
        try:
            # loads from yaml
            with open(self._root_dir / self._file_path, "r") as f:
                object.__setattr__(self, "_file_content", f.read())
            config_data = yaml.load(self._file_content)
            config = self._schema.model_validate(config_data)
        
        except FileNotFoundError:
            # loads defaults
            config = self._schema()
        
        # loads to delegate
        self._set_delegate(config)
        
    def save_to_yaml(self):
        """Saves config to YAML file."""
        
        from ruamel.yaml import YAML
        yaml = YAML()
        
        with open(self._root_dir / self._file_path, "w") as f:
            try:
                config = self._get_delegate()
                config_data = config.model_dump(
                    mode="json",
                    exclude={"env": True})
                yaml.dump(config_data, f)
                
            except Exception:
                # rewrites original content if YAML dump fails
                if self._file_content:
                    f.seek(0)
                    f.truncate()
                    f.write(self._file_content)
                raise
            
    def wipe(self):
        """Deletes config file and private key PEM file."""
        
        try:
            os.remove(self._root_dir / self._file_path)
        except FileNotFoundError:
            pass
        
        try:
            os.remove(self._root_dir / self.koi_net.private_key_pem_path)
        except FileNotFoundError:
            pass
    
    @contextmanager
    def mutate(self):
        """Helper method to modify and write config changes."""
        
        yield self._get_delegate()
        self.save_to_yaml()
        
    def start(self):
        """Saves default config to disk on startup."""
        
        self.save_to_yaml()