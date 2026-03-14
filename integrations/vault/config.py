"""Vault configuration from environment variables."""

import os


class VaultConfig:
    """Configuration for the Vault Agent, loaded from environment variables."""

    def __init__(self) -> None:
        self.master_secret: str = self._require("VAULT_MASTER_SECRET")
        self.db_host: str = os.getenv("VAULT_DB_HOST", "localhost")
        self.db_port: int = int(os.getenv("VAULT_DB_PORT", "5432"))
        self.db_name: str = os.getenv("VAULT_DB_NAME", "fiscalai_vault")
        self.db_user: str = os.getenv("VAULT_DB_USER", "vault")
        self.db_password: str = self._require("VAULT_DB_PASSWORD")
        self.redis_host: str = os.getenv("VAULT_REDIS_HOST", "localhost")
        self.redis_port: int = int(os.getenv("VAULT_REDIS_PORT", "6379"))
        self.redis_db: int = int(os.getenv("VAULT_REDIS_DB", "0"))
        self.pbkdf2_iterations: int = int(
            os.getenv("VAULT_PBKDF2_ITERATIONS", "100000")
        )
        self.expiry_warning_days: int = int(
            os.getenv("VAULT_EXPIRY_WARNING_DAYS", "30")
        )

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @staticmethod
    def _require(var_name: str) -> str:
        value = os.getenv(var_name)
        if not value:
            raise EnvironmentError(
                f"Required environment variable {var_name} is not set"
            )
        return value
