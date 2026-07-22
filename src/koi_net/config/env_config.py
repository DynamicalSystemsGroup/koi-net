from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvConfig(BaseSettings):
    """Config for environment variables.

    Variables set in this config class will be validated against the
    environment that the code is executed in. Names are case insensitive,
    so :attr:`.priv_key_password` would validate ``PRIV_KEY_PASSWORD`` in the
    environment.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )
    
    priv_key_password: str