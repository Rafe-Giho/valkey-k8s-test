# Valkey Cache Tester

FastAPI service for simple cache testing against Valkey deployments.

Supported connection modes:
- `standalone`: direct write host and optional separate read host
- `sentinel`: Sentinel-based primary discovery and replica reads
- `cluster`: Valkey Cluster with cluster-aware client

What the API does:
- write a cache item
- read a cache item from write or read path
- delete a cache item
- seed sample test keys
- run a roundtrip test that writes once and reads from both paths
- expose readiness and connection info

## Files

- App entrypoint: `app/main.py`
- Docker build: `Dockerfile`
- K8s base manifests: `k8s/base`
- K8s overlays:
  - `k8s/overlays/replication`
  - `k8s/overlays/sentinel`
  - `k8s/overlays/cluster`

## Build

```powershell
docker build -t <registry>/valkey-cache-tester:0.1.0 .\valkey-cache-tester
docker push <registry>/valkey-cache-tester:0.1.0
```

After pushing, update the image in:
- `k8s/base/deployment.yaml`

## Run locally

```powershell
Set-Location .\valkey-cache-tester
$env:VALKEY_MODE="standalone"
$env:VALKEY_HOST="127.0.0.1"
$env:VALKEY_PORT="6379"
$env:VALKEY_READ_HOST="127.0.0.1"
$env:VALKEY_READ_PORT="6379"
$env:VALKEY_USERNAME="default"
$env:VALKEY_PASSWORD="change-me"
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## API examples

```powershell
curl.exe http://localhost:8080/health/ready
```

```powershell
curl.exe -X POST http://localhost:8080/cache/items `
  -H "Content-Type: application/json" `
  -d "{\"key\":\"demo\",\"value\":{\"message\":\"hello\"},\"ttl_seconds\":300}"
```

```powershell
curl.exe http://localhost:8080/cache/items/demo?source=write
curl.exe http://localhost:8080/cache/items/demo?source=read
```

```powershell
curl.exe -X POST http://localhost:8080/cache/seed `
  -H "Content-Type: application/json" `
  -d "{\"prefix\":\"sample\",\"count\":5,\"ttl_seconds\":300}"
```

```powershell
curl.exe -X POST http://localhost:8080/cache/roundtrip `
  -H "Content-Type: application/json" `
  -d "{\"ttl_seconds\":120,\"read_attempts\":5,\"read_delay_ms\":200}"
```

## Kubernetes deployment

Replication overlay:

```powershell
kubectl apply -k .\valkey-cache-tester\k8s\overlays\replication
```

Sentinel overlay:

```powershell
kubectl apply -k .\valkey-cache-tester\k8s\overlays\sentinel
```

Cluster overlay:

```powershell
kubectl apply -k .\valkey-cache-tester\k8s\overlays\cluster
```

Each overlay assumes the target Valkey deployment already exists in its namespace:
- replication: namespace `valkey`, services `valkey` and `valkey-read`
- sentinel: namespace `valkey-sentinel-ha`, service `valkey-sentinel`
- cluster: namespace `valkey-cluster-ha`, service `valkey-cluster`

Before applying:
- set the image in `k8s/base/deployment.yaml`
- set the real password in `k8s/base/secret.yaml`
