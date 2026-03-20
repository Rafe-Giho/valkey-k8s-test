# Cluster 버전 전환 및 PowerShell 테스트 가이드

이 문서는 현재 아래 파일들로 배포된 Helm 기반 replication 환경을 내리고:

- `deployments/replication-helm-nks/nks-csi-storageclass.yaml`
- `deployments/replication-helm-nks/valkey-auth-secret.yaml`
- `deployments/replication-helm-nks/valkey-values-nks.yaml`

새로 만든 Valkey Cluster HA 구성으로 전환한 뒤, `apps/valkey-cache-tester` 앱으로 테스트하는 과정을 PowerShell 기준으로 설명합니다.

이 가이드의 대상 파일:

- Valkey Cluster HA: `deployments/cluster-ha`
- Cache Tester Cluster overlay: `apps/valkey-cache-tester/k8s/overlays/cluster`

## 1. 작업 폴더 이동

```powershell
Set-Location c:\Users\user\Desktop\신기호\업무용\30.PoC\valkey
```

## 2. 현재 Helm 기반 replication 배포 제거

현재 release 이름이 `valkey`, namespace가 `valkey`라고 가정합니다.

먼저 현재 테스트 앱이 떠 있다면 내립니다.

```powershell
kubectl delete -k .\apps\valkey-cache-tester\k8s\overlays\replication --ignore-not-found
```

그 다음 현재 Helm release를 삭제합니다.

```powershell
helm uninstall valkey -n valkey
```

삭제 후 상태 확인:

```powershell
kubectl get all -n valkey
kubectl get pvc -n valkey
```

중요:

- StatefulSet 기반 PVC는 남아 있을 수 있습니다.
- 완전히 새로 테스트하려면 남은 PVC를 직접 삭제해야 합니다.

완전 초기화가 필요할 때만 실행:

```powershell
kubectl delete pvc --all -n valkey
```

StorageClass는 그대로 재사용합니다.

## 3. Cluster HA 비밀번호 설정

아래 파일의 비밀번호를 실제 값으로 수정합니다.

- `deployments/cluster-ha/secret.yaml`

예시:

```yaml
stringData:
  password: 실제-비밀번호
```

## 4. Cache Tester 비밀번호도 동일하게 설정

아래 파일의 값을 Cluster 비밀번호와 동일하게 맞춥니다.

- `apps/valkey-cache-tester/k8s/base/secret.yaml`

예시:

```yaml
stringData:
  VALKEY_PASSWORD: 실제-비밀번호
```

## 5. Cache Tester 이미지 준비

```powershell
$Image = "<registry>/valkey-cache-tester:0.1.0"

docker build -t $Image .\apps\valkey-cache-tester
docker push $Image
```

그 다음 아래 파일에서 이미지를 실제 경로로 수정합니다.

- `apps/valkey-cache-tester/k8s/base/deployment.yaml`

## 6. Cluster HA 배포

```powershell
kubectl apply -k .\deployments\cluster-ha
```

상태 확인:

```powershell
kubectl get pods -n valkey-cluster-ha
kubectl get svc -n valkey-cluster-ha
kubectl get jobs -n valkey-cluster-ha
kubectl get pvc -n valkey-cluster-ha
```

기대 상태:

- Valkey Pod 6개
- bootstrap Job 생성
- PVC가 `Bound`

Job 완료 여부 확인:

```powershell
kubectl get jobs -n valkey-cluster-ha
kubectl logs -n valkey-cluster-ha job/valkey-cluster-bootstrap
```

## 7. Cluster 상태 직접 확인

아래 명령으로 cluster가 정상 생성됐는지 봅니다.

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER INFO
```

기대 결과:

- `cluster_state:ok`

노드 구성 확인:

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES
```

기대 결과:

- primary 3개
- replica 3개

## 8. Cache Tester Cluster overlay 배포

```powershell
kubectl apply -k .\apps\valkey-cache-tester\k8s\overlays\cluster
kubectl get pods -n valkey-cluster-ha
kubectl get svc -n valkey-cluster-ha
```

기대 상태:

- `valkey-cache-tester` Pod가 `Running`

## 9. 포트포워딩

별도 PowerShell 창에서 아래 명령을 실행하고 유지합니다.

```powershell
kubectl port-forward -n valkey-cluster-ha svc/valkey-cache-tester 8080:8080
```

## 10. 테스트 변수 준비

다른 PowerShell 창에서 아래 변수를 준비합니다.

```powershell
$BaseUrl = "http://127.0.0.1:8080"
$Headers = @{
    "Content-Type" = "application/json"
}
```

## 11. Cluster 연결 상태 확인

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/live"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/connection-info"
```

기대 결과:

- `mode`가 `cluster`
- seed endpoint 정보가 보임
- write/read ping이 성공

## 12. 데이터 쓰기

```powershell
$Body = @{
    key = "demo-cluster"
    value = @{
        message = "hello"
        source = "cluster"
    }
    ttl_seconds = 300
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/items" -Headers $Headers -Body $Body
```

## 13. write/read 조회

write 경로:

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=write"
```

read 경로:

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=read"
```

중요:

- Cluster에서는 앱이 cluster-aware client로 접속합니다.
- `read`는 클라이언트가 replica read를 지원할 때 replica 쪽으로 갈 수 있습니다.
- 설치된 Python 클라이언트 기능에 따라 `read`가 primary 경로로 fallback될 수도 있습니다.

## 14. roundtrip 테스트

```powershell
$RoundTripBody = @{
    ttl_seconds = 120
    read_attempts = 5
    read_delay_ms = 200
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/roundtrip" -Headers $Headers -Body $RoundTripBody
```

기대 결과:

- write 성공
- read 성공

## 15. 샘플 데이터 적재

```powershell
$SeedBody = @{
    prefix = "sample"
    count = 5
    ttl_seconds = 300
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/seed" -Headers $Headers -Body $SeedBody
```

## 16. 장애 테스트 상세 가이드

이 섹션도 실제 테스트 결과를 기록하지 않습니다. 각 장애 시나리오에서 정상적으로 보이면 어떤 현상이 나와야 하는지만 정리합니다.

### 16-1. 현재 cluster 상태 기준선 확인

장애 테스트 전에 반드시 현재 슬롯과 역할 상태를 기록합니다.

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER INFO

kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES
```

정상적으로 보면:

- `cluster_state:ok`
- primary 3개, replica 3개
- 각 primary마다 replica 1개가 매칭되어 있어야 합니다.

### 16-2. replica Pod 장애 테스트

replica Pod 하나를 삭제합니다.

```powershell
kubectl delete pod -n valkey-cluster-ha <replica-pod명>
```

재확인:

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER INFO

kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES

Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
```

정상적으로 보면:

- `cluster_state:ok`는 유지되어야 합니다.
- 해당 shard의 primary는 계속 write를 받아야 합니다.
- 삭제된 replica가 없어도 primary가 살아 있는 동안 전체 서비스는 계속 동작할 수 있습니다.
- replica Pod가 다시 뜨면 cluster에 replica로 다시 합류해야 합니다.

### 16-3. primary Pod 장애 테스트

현재 primary 하나를 선택해 삭제합니다.

```powershell
kubectl delete pod -n valkey-cluster-ha <primary-pod명>
```

재확인:

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER INFO

kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES

Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=write"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=read"
```

정상적으로 보면:

- 해당 primary의 replica가 새 primary로 승격되어야 합니다.
- 승격 직후 잠깐 응답 지연이나 일부 키에 대한 짧은 실패가 있을 수 있습니다.
- 하지만 일정 시간 후 `cluster_state:ok`로 돌아와야 합니다.
- cluster-aware client는 새 topology를 따라가면서 다시 write/read가 가능해져야 합니다.

### 16-4. 같은 shard의 primary와 replica를 모두 잃는 테스트

같은 shard에 속한 primary와 replica를 둘 다 내리는 시나리오입니다.

```powershell
kubectl delete pod -n valkey-cluster-ha <primary-pod명>
kubectl delete pod -n valkey-cluster-ha <그-primary의-replica-pod명>
```

재확인:

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER INFO

kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES
```

정상적으로 보면:

- 이 경우 slot coverage가 깨질 수 있습니다.
- 즉, 일부 키에 대한 요청 실패가 발생하는 것이 정상적인 관찰 결과입니다.
- `cluster_state:fail` 또는 slot 불완전 상태가 보일 수 있습니다.
- 이 상태는 cluster가 망가진 것이 아니라, 해당 shard를 복구할 replica가 없기 때문에 예상 가능한 결과입니다.

### 16-5. 노드 복구 후 재합류 확인

삭제했던 Pod가 다시 뜬 뒤 cluster에 어떻게 합류하는지 봅니다.

```powershell
kubectl get pods -n valkey-cluster-ha
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES
```

정상적으로 보면:

- 재시작한 Pod는 기존 cluster metadata에 따라 다시 적절한 역할로 붙어야 합니다.
- replica로 복귀하거나, 승격된 새 primary 아래로 재합류하는 형태가 보여야 합니다.

### 16-6. 앱 기준 최종 확인

장애 테스트 후 앱 상태를 다시 확인합니다.

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=write"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=read"
```

정상적으로 보면:

- cluster가 정상 coverage를 유지하는 시나리오에서는 앱 read/write가 다시 성공해야 합니다.
- coverage가 깨진 시나리오에서는 일부 요청이 실패할 수 있으며, 그 역시 예상된 관찰 결과입니다.

## 17. 정리

Cluster 환경 삭제:

```powershell
kubectl delete -k .\apps\valkey-cache-tester\k8s\overlays\cluster --ignore-not-found
kubectl delete -k .\deployments\cluster-ha --ignore-not-found
```

PVC까지 지우고 싶으면:

```powershell
kubectl delete pvc --all -n valkey-cluster-ha
```

## 18. 자주 보는 문제

bootstrap Job이 완료되지 않음:

- Pod 6개가 모두 준비되기 전에 Job이 실행됨
- DNS 또는 서비스 이름이 맞지 않음
- 비밀번호가 맞지 않음

`CLUSTER INFO`가 `ok`가 아님:

- cluster create가 정상 완료되지 않음
- 일부 node가 준비되지 않음

앱 write/read 실패:

- `apps/valkey-cache-tester/k8s/base/secret.yaml` 비밀번호 불일치
- Cluster seed 서비스가 준비되지 않음
- 클라이언트가 replica read를 완전히 지원하지 않아 read가 fallback될 수 있음
