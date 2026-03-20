from typing import Any, Literal

from pydantic import BaseModel, Field


class CacheSetRequest(BaseModel):
    key: str = Field(min_length=1, max_length=256)
    value: Any
    ttl_seconds: int | None = Field(default=None, ge=1)


class CacheSeedRequest(BaseModel):
    prefix: str = Field(default="sample", min_length=1, max_length=64)
    count: int = Field(default=10, ge=1, le=100)
    ttl_seconds: int | None = Field(default=None, ge=1)


class CacheRoundTripRequest(BaseModel):
    key: str | None = Field(default=None, max_length=256)
    ttl_seconds: int | None = Field(default=None, ge=1)
    read_attempts: int = Field(default=5, ge=1, le=20)
    read_delay_ms: int = Field(default=200, ge=0, le=5000)


class CacheItemResponse(BaseModel):
    key: str
    storage_key: str
    source: Literal["write", "read"]
    exists: bool
    ttl_seconds: int | None
    payload: Any | None

