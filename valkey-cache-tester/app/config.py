from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "valkey-cache-tester"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    valkey_mode: Literal["standalone", "sentinel", "cluster"] = "standalone"
    valkey_username: str = "default"
    valkey_password: str = ""
    valkey_db: int = 0
    valkey_socket_timeout: float = 5.0

    valkey_host: str = "valkey"
    valkey_port: int = 6379
    valkey_read_host: str = ""
    valkey_read_port: int = 6379

    valkey_sentinel_master_name: str = "mymaster"
    valkey_sentinel_hosts: str = "valkey-sentinel:26379"
    valkey_sentinel_username: str = ""
    valkey_sentinel_password: str = ""

    valkey_cluster_nodes: str = "valkey-cluster:6379"

    cache_key_prefix: str = "cache-test"
    default_ttl_seconds: int = Field(default=300, ge=1)

    @property
    def write_endpoint(self) -> tuple[str, int]:
        return self.valkey_host, self.valkey_port

    @property
    def read_endpoint(self) -> tuple[str, int]:
        host = self.valkey_read_host or self.valkey_host
        port = self.valkey_read_port or self.valkey_port
        return host, port

    @property
    def sentinel_endpoints(self) -> list[tuple[str, int]]:
        return [self._parse_host_port(node, 26379) for node in self.valkey_sentinel_hosts.split(",") if node.strip()]

    @property
    def cluster_endpoints(self) -> list[tuple[str, int]]:
        return [self._parse_host_port(node, 6379) for node in self.valkey_cluster_nodes.split(",") if node.strip()]

    @staticmethod
    def _parse_host_port(value: str, default_port: int) -> tuple[str, int]:
        raw = value.strip()
        if not raw:
            raise ValueError("Empty host value is not allowed")
        if ":" not in raw:
            return raw, default_port
        host, port = raw.rsplit(":", 1)
        return host.strip(), int(port.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
