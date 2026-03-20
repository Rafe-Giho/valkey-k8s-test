import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import valkey

from app.config import Settings

logger = logging.getLogger(__name__)


def _resolve_direct_client_class() -> type[Any]:
    for name in ("Valkey", "Redis"):
        client_class = getattr(valkey, name, None)
        if client_class is not None:
            return client_class
    raise RuntimeError("Direct Valkey client class not found in installed valkey package")


def _resolve_cluster_client_class() -> type[Any]:
    candidates: list[type[Any]] = []
    for attr in ("ValkeyCluster", "RedisCluster"):
        direct = getattr(valkey, attr, None)
        if direct is not None:
            candidates.append(direct)
    try:
        from valkey.cluster import ValkeyCluster  # type: ignore

        candidates.append(ValkeyCluster)
    except Exception:
        pass
    try:
        from valkey.cluster import RedisCluster  # type: ignore

        candidates.append(RedisCluster)
    except Exception:
        pass
    if not candidates:
        raise RuntimeError("Valkey cluster client class not found in installed valkey package")
    return candidates[0]


def _resolve_sentinel_class() -> type[Any]:
    try:
        from valkey.sentinel import Sentinel  # type: ignore

        return Sentinel
    except Exception as exc:
        raise RuntimeError("Valkey Sentinel client support is not available") from exc


class CacheService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._write_client: Any | None = None
        self._read_client: Any | None = None
        self._sentinel: Any | None = None

    def warmup(self) -> None:
        self._ensure_clients()
        self.ping()

    def close(self) -> None:
        for client in (self._write_client, self._read_client):
            if client is None:
                continue
            close_method = getattr(client, "close", None)
            if callable(close_method):
                close_method()
        self._write_client = None
        self._read_client = None
        self._sentinel = None

    def get_connection_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "mode": self.settings.valkey_mode,
            "cache_key_prefix": self.settings.cache_key_prefix,
        }
        if self.settings.valkey_mode == "standalone":
            info["write_endpoint"] = self.settings.write_endpoint
            info["read_endpoint"] = self.settings.read_endpoint
        elif self.settings.valkey_mode == "sentinel":
            info["sentinel_endpoints"] = self.settings.sentinel_endpoints
            info["sentinel_master_name"] = self.settings.valkey_sentinel_master_name
        else:
            info["cluster_endpoints"] = self.settings.cluster_endpoints
        return info

    def ping(self) -> dict[str, Any]:
        write_client, read_client = self._ensure_clients()
        return {
            "mode": self.settings.valkey_mode,
            "write": self._ping_client(write_client, "write"),
            "read": self._ping_client(read_client, "read"),
        }

    def set_item(self, key: str, value: Any, ttl_seconds: int | None) -> dict[str, Any]:
        write_client, _ = self._ensure_clients()
        storage_key = self._build_storage_key(key)
        ttl = ttl_seconds or self.settings.default_ttl_seconds
        payload = self._serialize_payload(key, value)
        write_client.set(storage_key, payload, ex=ttl)
        return self.get_item(key, "write")

    def get_item(self, key: str, source: Literal["write", "read"]) -> dict[str, Any]:
        write_client, read_client = self._ensure_clients()
        storage_key = self._build_storage_key(key)
        client = write_client if source == "write" else read_client
        raw_value = client.get(storage_key)
        ttl = client.ttl(storage_key)
        return {
            "key": key,
            "storage_key": storage_key,
            "source": source,
            "exists": raw_value is not None,
            "ttl_seconds": self._normalize_ttl(ttl),
            "payload": self._deserialize_payload(raw_value),
        }

    def delete_item(self, key: str) -> dict[str, Any]:
        write_client, _ = self._ensure_clients()
        storage_key = self._build_storage_key(key)
        deleted = write_client.delete(storage_key)
        return {
            "key": key,
            "storage_key": storage_key,
            "deleted": bool(deleted),
        }

    def seed_items(self, prefix: str, count: int, ttl_seconds: int | None) -> dict[str, Any]:
        ttl = ttl_seconds or self.settings.default_ttl_seconds
        seeded_keys: list[str] = []
        for index in range(count):
            key = f"{prefix}-{index + 1}"
            value = {
                "index": index + 1,
                "prefix": prefix,
                "token": str(uuid.uuid4()),
            }
            self.set_item(key, value, ttl)
            seeded_keys.append(key)
        return {
            "count": count,
            "ttl_seconds": ttl,
            "keys": seeded_keys,
        }

    def roundtrip(self, key: str | None, ttl_seconds: int | None, read_attempts: int, read_delay_ms: int) -> dict[str, Any]:
        actual_key = key or f"roundtrip-{uuid.uuid4().hex[:12]}"
        ttl = ttl_seconds or self.settings.default_ttl_seconds
        payload = {
            "message": "valkey-cache-tester",
            "token": str(uuid.uuid4()),
            "requested_mode": self.settings.valkey_mode,
        }
        write_result = self.set_item(actual_key, payload, ttl)
        read_result = None
        for attempt in range(1, read_attempts + 1):
            read_result = self.get_item(actual_key, "read")
            if read_result["exists"]:
                read_result["attempt"] = attempt
                break
            if attempt < read_attempts and read_delay_ms > 0:
                time.sleep(read_delay_ms / 1000)
        return {
            "write": write_result,
            "read": read_result,
            "replica_visible": bool(read_result and read_result["exists"]),
        }

    def _ensure_clients(self) -> tuple[Any, Any]:
        if self._write_client is not None and self._read_client is not None:
            return self._write_client, self._read_client
        with self._lock:
            if self._write_client is not None and self._read_client is not None:
                return self._write_client, self._read_client
            if self.settings.valkey_mode == "standalone":
                self._write_client, self._read_client = self._create_standalone_clients()
            elif self.settings.valkey_mode == "sentinel":
                self._write_client, self._read_client = self._create_sentinel_clients()
            elif self.settings.valkey_mode == "cluster":
                self._write_client, self._read_client = self._create_cluster_clients()
            else:
                raise ValueError(f"Unsupported mode: {self.settings.valkey_mode}")
            return self._write_client, self._read_client

    def _create_standalone_clients(self) -> tuple[Any, Any]:
        client_class = _resolve_direct_client_class()
        write_host, write_port = self.settings.write_endpoint
        read_host, read_port = self.settings.read_endpoint
        write_client = client_class(
            host=write_host,
            port=write_port,
            db=self.settings.valkey_db,
            username=self.settings.valkey_username or None,
            password=self.settings.valkey_password or None,
            decode_responses=True,
            socket_timeout=self.settings.valkey_socket_timeout,
        )
        read_client = client_class(
            host=read_host,
            port=read_port,
            db=self.settings.valkey_db,
            username=self.settings.valkey_username or None,
            password=self.settings.valkey_password or None,
            decode_responses=True,
            socket_timeout=self.settings.valkey_socket_timeout,
        )
        return write_client, read_client

    def _create_sentinel_clients(self) -> tuple[Any, Any]:
        sentinel_class = _resolve_sentinel_class()
        sentinel_kwargs: dict[str, Any] = {}
        if self.settings.valkey_sentinel_username:
            sentinel_kwargs["username"] = self.settings.valkey_sentinel_username
        if self.settings.valkey_sentinel_password:
            sentinel_kwargs["password"] = self.settings.valkey_sentinel_password

        init_kwargs: dict[str, Any] = {
            "socket_timeout": self.settings.valkey_socket_timeout,
        }
        if sentinel_kwargs:
            init_kwargs["sentinel_kwargs"] = sentinel_kwargs

        try:
            self._sentinel = sentinel_class(self.settings.sentinel_endpoints, **init_kwargs)
        except TypeError:
            self._sentinel = sentinel_class(self.settings.sentinel_endpoints, socket_timeout=self.settings.valkey_socket_timeout)

        common_kwargs = {
            "db": self.settings.valkey_db,
            "username": self.settings.valkey_username or None,
            "password": self.settings.valkey_password or None,
            "decode_responses": True,
            "socket_timeout": self.settings.valkey_socket_timeout,
        }
        write_client = self._sentinel.master_for(self.settings.valkey_sentinel_master_name, **common_kwargs)
        read_client = self._sentinel.slave_for(self.settings.valkey_sentinel_master_name, **common_kwargs)
        return write_client, read_client

    def _create_cluster_clients(self) -> tuple[Any, Any]:
        write_client = self._build_cluster_client(read_from_replicas=False)
        try:
            read_client = self._build_cluster_client(read_from_replicas=True)
        except Exception:
            logger.warning("Cluster read replica mode is not supported by the installed client, falling back to the default cluster client")
            read_client = write_client
        return write_client, read_client

    def _build_cluster_client(self, read_from_replicas: bool) -> Any:
        cluster_class = _resolve_cluster_client_class()
        last_error: Exception | None = None
        optional_variants = [
            {
                "read_from_replicas": read_from_replicas,
                "skip_full_coverage_check": True,
                "socket_timeout": self.settings.valkey_socket_timeout,
            },
            {
                "read_from_replicas": read_from_replicas,
                "socket_timeout": self.settings.valkey_socket_timeout,
            },
            {
                "socket_timeout": self.settings.valkey_socket_timeout,
            },
            {},
        ]

        for host, port in self.settings.cluster_endpoints:
            base_kwargs = {
                "host": host,
                "port": port,
                "username": self.settings.valkey_username or None,
                "password": self.settings.valkey_password or None,
                "decode_responses": True,
            }
            for extra in optional_variants:
                kwargs = {**base_kwargs, **extra}
                try:
                    return cluster_class(**kwargs)
                except TypeError as exc:
                    last_error = exc
                except Exception as exc:
                    last_error = exc
        if last_error is None:
            raise RuntimeError("Failed to create a Valkey cluster client")
        raise last_error

    def _build_storage_key(self, key: str) -> str:
        prefix = self.settings.cache_key_prefix.strip(":")
        if not prefix:
            return key
        return f"{prefix}:{key}"

    def _serialize_payload(self, key: str, value: Any) -> str:
        payload = {
            "key": key,
            "value": value,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.settings.valkey_mode,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _deserialize_payload(raw_value: Any) -> Any:
        if raw_value is None:
            return None
        if not isinstance(raw_value, str):
            return raw_value
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value

    @staticmethod
    def _normalize_ttl(ttl_value: Any) -> int | None:
        if ttl_value in (-2, None):
            return None
        if ttl_value == -1:
            return None
        return int(ttl_value)

    def _ping_client(self, client: Any, source: Literal["write", "read"]) -> dict[str, Any]:
        ping_value = client.ping()
        info: dict[str, Any] = {
            "source": source,
            "ping": ping_value,
        }
        if self.settings.valkey_mode != "cluster":
            try:
                role = client.role()
                if isinstance(role, (list, tuple)) and role:
                    info["role"] = role[0]
                else:
                    info["role"] = role
            except Exception:
                info["role"] = "unknown"
        return info
