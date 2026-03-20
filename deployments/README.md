# Deployments

이 폴더는 Valkey 배포 구성을 아키텍처별로 분리해둔 영역입니다.

## 하위 폴더

### `replication-helm-nks`

목적:
- NHN Cloud NKS에서 공식 Valkey Helm chart를 사용해 primary-replica 복제 구성을 올리기 위한 파일 모음

주요 파일:
- `nks-csi-storageclass.yaml`
- `valkey-auth-secret.yaml`
- `valkey-values-nks.yaml`
- `valkey-values.yaml`
- `README.md`

### `sentinel-ha`

목적:
- raw Kubernetes manifests로 Sentinel 기반 HA 구성을 올리기 위한 파일 모음

주요 파일:
- `statefulset-valkey.yaml`
- `statefulset-sentinel.yaml`
- `configmap-valkey.yaml`
- `configmap-sentinel.yaml`
- `services.yaml`
- `secret.yaml`
- `README.md`

### `cluster-ha`

목적:
- raw Kubernetes manifests로 Valkey Cluster 기반 HA 구성을 올리기 위한 파일 모음

주요 파일:
- `statefulset.yaml`
- `job-bootstrap.yaml`
- `configmap.yaml`
- `services.yaml`
- `secret.yaml`
- `README.md`

## 선택 기준

- 읽기 분산 정도만 필요하고 기존 Redis/Valkey replication 방식에 익숙하면:
  - `replication-helm-nks`
- 자동 failover가 필요하지만 샤딩은 필요 없으면:
  - `sentinel-ha`
- 샤딩과 HA를 같이 원하면:
  - `cluster-ha`
