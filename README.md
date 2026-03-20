# Valkey 실험 환경 정리

이 저장소는 Valkey를 여러 아키텍처로 Kubernetes에 배포하고, FastAPI 기반 테스트 앱으로 읽기/쓰기 동작을 검증하기 위한 작업 공간입니다.

## 폴더 구조

```text
.
├─ deployments/
│  ├─ replication-helm-nks/   # NHN Cloud NKS용 Helm 기반 primary-replica 배포
│  ├─ sentinel-ha/            # Sentinel 기반 HA 배포
│  └─ cluster-ha/             # Cluster 기반 HA 배포
├─ apps/
│  └─ valkey-cache-tester/    # FastAPI 테스트 서비스 및 배포 가이드
└─ vendor/
   └─ valkey-helm/            # 참고용 공식 Helm chart 소스
```

## 아키텍처 요약

### 1. Replication + Helm + NKS

위치:
- `deployments/replication-helm-nks`

특징:
- 공식 Valkey Helm chart 기반
- `1 primary + N replicas`
- 읽기 서비스와 쓰기 서비스 분리 가능
- 자동 failover 없음
- NKS PoC나 기본 복제 테스트에 적합

### 2. Sentinel HA

위치:
- `deployments/sentinel-ha`

특징:
- `3 Valkey + 3 Sentinel`
- 비-cluster primary-replica 구조
- Sentinel이 primary 장애를 감지하고 replica를 승격
- 클라이언트는 Sentinel-aware 여야 함
- 샤딩은 하지 않음

### 3. Cluster HA

위치:
- `deployments/cluster-ha`

특징:
- `6 Valkey 노드`
- `3 primary + 3 replica`
- 슬롯 기반 샤딩
- 클러스터 자체 failover
- 클라이언트는 cluster-aware 여야 함

### 4. Cache Tester

위치:
- `apps/valkey-cache-tester`

특징:
- FastAPI 기반 테스트 앱
- standalone / sentinel / cluster 모드 지원
- 캐시 쓰기, 읽기, 삭제, seed, roundtrip 테스트 제공
- Kubernetes overlay로 각 아키텍처에 맞게 연결 가능

## 어디서 시작하면 되는지

- 현재 Helm 기반 NKS replication 구성을 보고 싶으면:
  - `deployments/replication-helm-nks/README.md`
- Sentinel 기반 HA를 보고 싶으면:
  - `deployments/sentinel-ha/README.md`
- Cluster 기반 HA를 보고 싶으면:
  - `deployments/cluster-ha/README.md`
- 테스트 앱과 테스트 가이드를 보고 싶으면:
  - `apps/valkey-cache-tester/README.md`

## 참고

- `vendor/valkey-helm`은 공식 Helm chart를 참고용으로 저장한 폴더입니다.
- 실제 운영용 수정은 `deployments` 아래 배포 폴더 기준으로 보는 것이 맞습니다.
