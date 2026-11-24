import json
from functools import lru_cache
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_NAME = "makelele-secrets"


class Settings(BaseSettings):
    # AWS Configuration
    AWS_REGION_NAME: str
    BUCKET_NAME: str

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        extra = "ignore"
    )

setting = Settings()

@lru_cache
def secret_cache():
    """Secrets Manager cache, refreshed every hour"""
    # Imported here because modules.aws.secrets_manager imports this module
    from modules.aws.secrets_manager import get_secret_manager
    return SecretCache(
        client = get_secret_manager(),
        config = SecretCacheConfig(secret_refresh_interval = 3600)
    )

def get_secret(name: str):
    """One value from the app secret, served from the cache"""
    return json.loads(secret_cache().get_secret_string(SECRETS_NAME))[name]
