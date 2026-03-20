# Valkey Cache Tester

Valkey 배포에 대해 간단한 캐시 읽기/쓰기 테스트를 수행하는 FastAPI 서비스입니다.

## 지원 연결 모드

- `standalone`: write host와 선택적 read host에 직접 연결
- `sentinel`: Sentinel을 통해 현재 primary와 replica를 찾음
- `cluster`: cluster-aware client로 Valkey Cluster에 연결

## 이 앱이 하는 일

- 캐시 항목 쓰기
- write 경로 또는 read 경로에서 캐시 조회
- 캐시 항목 삭제
- 샘플 테스트 데이터 적재
- write 후 read까지 확인하는 roundtrip 테스트
- readiness와 연결 정보 확인

## 아키텍처 관점에서 보는 역할

- replication 배포에서는 `valkey`와 `valkey-read`를 각각 write/read 경로로 사용합니다
- sentinel 배포에서는 Sentinel이 현재 primary와 replica를 찾아줍니다
- cluster 배포에서는 cluster-aware client로 seed endpoint에 붙습니다

즉, 이 앱은 Valkey 아키텍처 자체를 구성하는 역할이 아니라, 이미 배포된 Valkey 구성이 정상적으로 동작하는지 검증하는 테스트 클라이언트 역할입니다.

## 주요 파일

- App entrypoint: `app/main.py`
- Docker build: `Dockerfile`
- K8s base manifests: `k8s/base`
- K8s overlays:
  - `k8s/overlays/replication`
  - `k8s/overlays/sentinel`
  - `k8s/overlays/cluster`

## 가이드 파일

- `TEST-GUIDE-current-replication.md`
  - 현재 Helm 기반 replication 배포를 대상으로 한 일반 테스트 가이드
- `TEST-GUIDE-current-replication-powershell.md`
  - 현재 Helm 기반 replication 배포를 대상으로 한 PowerShell 전용 가이드
- `TEST-GUIDE-sentinel-powershell.md`
  - replication 환경을 내리고 Sentinel HA 구성으로 전환해 테스트하는 PowerShell 가이드
- `TEST-GUIDE-cluster-powershell.md`
  - replication 환경을 내리고 Cluster HA 구성으로 전환해 테스트하는 PowerShell 가이드

## Build

```powershell
docker build -t <registry>/valkey-cache-tester:0.1.0 .\apps\valkey-cache-tester
docker push <registry>/valkey-cache-tester:0.1.0
```

이미지 푸시 후 아래 파일의 이미지를 실제 값으로 수정합니다.
- `k8s/base/deployment.yaml`

## Run locally

```powershell
Set-Location .\apps\valkey-cache-tester
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
kubectl apply -k .\apps\valkey-cache-tester\k8s\overlays\replication
```

Sentinel overlay:

```powershell
kubectl apply -k .\apps\valkey-cache-tester\k8s\overlays\sentinel
```

Cluster overlay:

```powershell
kubectl apply -k .\apps\valkey-cache-tester\k8s\overlays\cluster
```

각 overlay는 대상 Valkey 배포가 먼저 올라와 있다고 가정합니다.

- replication: namespace `valkey`, services `valkey` and `valkey-read`
- sentinel: namespace `valkey-sentinel-ha`, service `valkey-sentinel`
- cluster: namespace `valkey-cluster-ha`, service `valkey-cluster`

관련 배포 위치:
- replication: `deployments/replication-helm-nks`
- sentinel: `deployments/sentinel-ha`
- cluster: `deployments/cluster-ha`

배포 전에:
- `k8s/base/deployment.yaml`의 이미지를 실제 이미지로 수정
- `k8s/base/secret.yaml`의 비밀번호를 실제 Valkey 비밀번호로 수정
