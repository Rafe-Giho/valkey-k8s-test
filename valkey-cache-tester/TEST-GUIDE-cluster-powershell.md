# Cluster 버전 전환 및 PowerShell 테스트 가이드

이 문서는 현재 아래 파일들로 배포된 Helm 기반 replication 환경을 내리고:

- `nks-csi-storageclass.yaml`
- `valkey-auth-secret.yaml`
- `valkey-values-nks.yaml`

새로 만든 Valkey Cluster HA 구성으로 전환한 뒤, `valkey-cache-tester`로 테스트하는 과정을 PowerShell 기준으로 설명합니다.

이 가이드의 대상 파일:

- Valkey Cluster HA: `k8s/valkey-cluster-ha`
- Cache Tester Cluster overlay: `valkey-cache-tester/k8s/overlays/cluster`

## 1. 작업 폴더 이동

```powershell
Set-Location c:\Users\user\Desktop\신기호\업무용\30.PoC\valkey
```

## 2. 현재 Helm 기반 replication 배포 제거

현재 release 이름이 `valkey`, namespace가 `valkey`라고 가정합니다.

먼저 현재 테스트 앱이 떠 있다면 내립니다.

```powershell
kubectl delete -k .\valkey-cache-tester\k8s\overlays\replication --ignore-not-found
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

- `k8s/valkey-cluster-ha/secret.yaml`

예시:

```yaml
stringData:
  password: 실제-비밀번호
```

## 4. Cache Tester 비밀번호도 동일하게 설정

아래 파일의 값을 Cluster 비밀번호와 동일하게 맞춥니다.

- `valkey-cache-tester/k8s/base/secret.yaml`

예시:

```yaml
stringData:
  VALKEY_PASSWORD: 실제-비밀번호
```

## 5. Cache Tester 이미지 준비

```powershell
$Image = "<registry>/valkey-cache-tester:0.1.0"

docker build -t $Image .\valkey-cache-tester
docker push $Image
```

그 다음 아래 파일에서 이미지를 실제 경로로 수정합니다.

- `valkey-cache-tester/k8s/base/deployment.yaml`

## 6. Cluster HA 배포

```powershell
kubectl apply -k .\k8s\valkey-cluster-ha
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
kubectl apply -k .\valkey-cache-tester\k8s\overlays\cluster
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

## 16. 장애 테스트 예시

현재 cluster node 상태 확인:

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES
```

primary 하나를 삭제합니다.

```powershell
kubectl delete pod -n valkey-cluster-ha <primary-pod명>
```

잠시 후 다시 cluster 상태를 확인합니다.

```powershell
kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER INFO

kubectl exec -n valkey-cluster-ha valkey-cluster-0 -- `
  valkey-cli -a <비밀번호> CLUSTER NODES
```

그 다음 앱 상태를 다시 확인합니다.

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=write"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-cluster?source=read"
```

## 17. 정리

Cluster 환경 삭제:

```powershell
kubectl delete -k .\valkey-cache-tester\k8s\overlays\cluster --ignore-not-found
kubectl delete -k .\k8s\valkey-cluster-ha --ignore-not-found
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

- `valkey-cache-tester/k8s/base/secret.yaml` 비밀번호 불일치
- Cluster seed 서비스가 준비되지 않음
- 클라이언트가 replica read를 완전히 지원하지 않아 read가 fallback될 수 있음
