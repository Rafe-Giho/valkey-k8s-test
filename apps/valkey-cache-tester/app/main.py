import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.clients import CacheService
from app.config import Settings, get_settings
from app.models import CacheItemResponse, CacheRoundTripRequest, CacheSeedRequest, CacheSetRequest


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    service = CacheService(settings)
    app.state.settings = settings
    app.state.cache_service = service
    try:
        await run_in_threadpool(service.warmup)
    except Exception as exc:
        logging.getLogger(__name__).warning("Initial Valkey warmup failed: %s", exc)
    yield
    await run_in_threadpool(service.close)


app = FastAPI(
    title="Valkey Cache Tester",
    version="0.1.0",
    description="Simple FastAPI service for write/read cache testing against Valkey",
    lifespan=lifespan,
)


def get_cache_service(request: Request) -> CacheService:
    return request.app.state.cache_service


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def call_service(func, *args, **kwargs):
    try:
        return await run_in_threadpool(func, *args, **kwargs)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/")
async def root(settings: Settings = Depends(get_app_settings)):
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "mode": settings.valkey_mode,
        "docs": "/docs",
    }


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness(service: CacheService = Depends(get_cache_service)):
    return await call_service(service.ping)


@app.get("/connection-info")
async def connection_info(service: CacheService = Depends(get_cache_service)):
    return await call_service(service.get_connection_info)


@app.post("/cache/items", response_model=CacheItemResponse)
async def set_cache_item(request_body: CacheSetRequest, service: CacheService = Depends(get_cache_service)):
    return await call_service(service.set_item, request_body.key, request_body.value, request_body.ttl_seconds)


@app.get("/cache/items/{key}", response_model=CacheItemResponse)
async def get_cache_item(
    key: str,
    source: str = Query(default="read", pattern="^(read|write)$"),
    service: CacheService = Depends(get_cache_service),
):
    return await call_service(service.get_item, key, source)


@app.delete("/cache/items/{key}")
async def delete_cache_item(key: str, service: CacheService = Depends(get_cache_service)):
    return await call_service(service.delete_item, key)


@app.post("/cache/seed")
async def seed_cache(request_body: CacheSeedRequest, service: CacheService = Depends(get_cache_service)):
    return await call_service(service.seed_items, request_body.prefix, request_body.count, request_body.ttl_seconds)


@app.post("/cache/roundtrip")
async def roundtrip_cache(request_body: CacheRoundTripRequest, service: CacheService = Depends(get_cache_service)):
    return await call_service(
        service.roundtrip,
        request_body.key,
        request_body.ttl_seconds,
        request_body.read_attempts,
        request_body.read_delay_ms,
    )
