# Sentinel HA

이 폴더는 raw Kubernetes manifests로 Valkey Sentinel 기반 HA 환경을 구성하기 위한 파일 모음입니다.

## 아키텍처

구성:
- Valkey 3개
- Sentinel 3개
- Valkey 데이터 PVC
- Sentinel 상태 PVC

동작 방식:
- 기본 구조는 primary-replica
- Sentinel이 현재 primary를 감시
- primary 장애 시 replica를 새 primary로 승격
- 클라이언트는 Sentinel에 현재 primary를 질의해서 접속

중요:
- 클라이언트는 Sentinel-aware 여야 합니다
- 이 구성은 샤딩이 아니라 failover 중심 구성입니다
- plain Service 하나만으로 write endpoint가 자동 전환되지는 않습니다

## 파일 설명

- `namespace.yaml`
  - 전용 namespace 생성
- `secret.yaml`
  - Valkey 인증 비밀번호 저장
- `services.yaml`
  - Valkey node headless service, Sentinel peer service, Sentinel discovery service 정의
- `configmap-valkey.yaml`
  - Valkey 시작 스크립트와 설정 생성 로직
- `statefulset-valkey.yaml`
  - Valkey 3개 Pod 배포 및 데이터 PVC 정의
- `configmap-sentinel.yaml`
  - Sentinel 시작 스크립트와 sentinel.conf 생성 로직
- `statefulset-sentinel.yaml`
  - Sentinel 3개 Pod 배포 및 Sentinel 상태 PVC 정의

## 배포

```powershell
kubectl apply -k .\deployments\sentinel-ha
```

## 확인 포인트

```powershell
kubectl get pods -n valkey-sentinel-ha
kubectl get svc -n valkey-sentinel-ha
kubectl get pvc -n valkey-sentinel-ha
```

## 주요 엔드포인트

- Sentinel discovery:
  - `valkey-sentinel.valkey-sentinel-ha.svc.cluster.local:26379`
- Valkey nodes:
  - `valkey-nodes.valkey-sentinel-ha.svc.cluster.local`
- Sentinel master name:
  - `mymaster`

## 언제 이 구성을 쓰는지

- 샤딩 없이 자동 failover가 필요할 때
- Redis/Valkey Sentinel 운영 방식에 익숙할 때
- 읽기/쓰기 역할을 나누되 primary 승격까지 검증하고 싶을 때
