# Cluster HA

이 폴더는 raw Kubernetes manifests로 Valkey Cluster 기반 HA 환경을 구성하기 위한 파일 모음입니다.

## 아키텍처

구성:
- Valkey 6개 노드
- bootstrap Job
- 각 노드별 PVC
- headless service + seed service

동작 방식:
- `3 primary + 3 replica`
- 슬롯 기반 샤딩
- cluster 자체 failover
- 클라이언트는 cluster-aware 여야 함

중요:
- Cluster는 Sentinel과 달리 샤딩이 포함됩니다
- 단일 Service는 seed endpoint 용도일 뿐, 전체 라우팅 계층이 아닙니다
- 클라이언트가 cluster redirection을 처리해야 합니다

## 파일 설명

- `namespace.yaml`
  - 전용 namespace 생성
- `secret.yaml`
  - Valkey 인증 비밀번호 저장
- `services.yaml`
  - headless node discovery service와 seed service 정의
- `configmap.yaml`
  - cluster 설정 파일 생성 스크립트
- `statefulset.yaml`
  - 6개 Valkey 노드와 PVC 정의
- `job-bootstrap.yaml`
  - 노드가 뜬 뒤 cluster create를 수행하는 bootstrap Job

## 배포

```powershell
kubectl apply -k .\deployments\cluster-ha
```

## 확인 포인트

```powershell
kubectl get pods -n valkey-cluster-ha
kubectl get svc -n valkey-cluster-ha
kubectl get jobs -n valkey-cluster-ha
kubectl get pvc -n valkey-cluster-ha
```

## 주요 엔드포인트

- Cluster seed service:
  - `valkey-cluster.valkey-cluster-ha.svc.cluster.local:6379`
- Headless node discovery:
  - `valkey-cluster-headless.valkey-cluster-ha.svc.cluster.local`

## 언제 이 구성을 쓰는지

- 데이터 샤딩이 필요할 때
- 클러스터 레벨 failover까지 검증하고 싶을 때
- 애플리케이션이 cluster-aware client를 사용할 수 있을 때
