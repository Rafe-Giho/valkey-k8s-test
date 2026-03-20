# Replication + Helm + NKS

이 폴더는 NHN Cloud NKS에서 공식 Valkey Helm chart를 사용해 primary-replica 구성을 배포할 때 사용하는 파일들을 모아둔 곳입니다.

## 아키텍처

구성:
- `1 primary + 2 replicas`
- 쓰기 서비스: `valkey`
- 읽기 서비스: `valkey-read`
- 인증 사용
- replica PVC 사용
- metrics exporter 사용

특징:
- 공식 Helm chart 기반이라 관리가 단순함
- 읽기/쓰기 분리를 빠르게 테스트할 수 있음
- 자동 failover는 없음
- Sentinel이나 Cluster가 아닌 기본 replication 구조

## 파일 설명

### `nks-csi-storageclass.yaml`

역할:
- NKS에서 PVC를 동적으로 생성할 StorageClass 정의

용도:
- replica PVC가 붙을 때 사용

### `valkey-auth-secret.yaml`

역할:
- Valkey ACL 사용자 비밀번호를 담는 Secret

용도:
- `default` 사용자 인증에 사용

### `valkey-values-nks.yaml`

역할:
- NKS 환경에 맞춘 Helm values 파일

포함 내용:
- image tag 고정
- auth 사용
- replica 2개
- replica persistence 설정
- anti-affinity
- metrics 활성화

### `valkey-values.yaml`

역할:
- 원본 values 참고본

용도:
- 기본 chart 값과 비교할 때 사용

## 배포 순서 예시

```powershell
kubectl create namespace valkey
kubectl apply -f .\deployments\replication-helm-nks\nks-csi-storageclass.yaml
kubectl apply -n valkey -f .\deployments\replication-helm-nks\valkey-auth-secret.yaml

helm repo add valkey https://valkey-io.github.io/valkey-helm/
helm repo update

helm upgrade --install valkey valkey/valkey `
  --namespace valkey `
  -f .\deployments\replication-helm-nks\valkey-values-nks.yaml `
  --wait `
  --timeout 10m
```

## 언제 이 구성을 쓰는지

- NKS에서 먼저 PoC를 빠르게 올리고 싶을 때
- 읽기/쓰기 분리 테스트가 목적일 때
- Sentinel이나 Cluster까지는 아직 필요 없을 때
- 운영 HA보다는 기본 복제 구성을 먼저 검증하고 싶을 때
