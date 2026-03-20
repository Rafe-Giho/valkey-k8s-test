# Sentinel 버전 전환 및 PowerShell 테스트 가이드

이 문서는 현재 아래 파일들로 배포된 Helm 기반 replication 환경을 내리고:

- `deployments/replication-helm-nks/nks-csi-storageclass.yaml`
- `deployments/replication-helm-nks/valkey-auth-secret.yaml`
- `deployments/replication-helm-nks/valkey-values-nks.yaml`

새로 만든 Sentinel HA 구성으로 전환한 뒤, `apps/valkey-cache-tester` 앱으로 테스트하는 과정을 PowerShell 기준으로 설명합니다.

이 가이드의 대상 파일:

- Valkey Sentinel HA: `deployments/sentinel-ha`
- Cache Tester Sentinel overlay: `apps/valkey-cache-tester/k8s/overlays/sentinel`

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

삭제 후 상태를 확인합니다.

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

StorageClass는 계속 재사용하므로 삭제하지 않습니다.

## 3. Sentinel HA 비밀번호 설정

아래 파일의 비밀번호를 실제 값으로 변경합니다.

- `deployments/sentinel-ha/secret.yaml`

예시:

```yaml
stringData:
  password: 실제-비밀번호
```

## 4. Cache Tester 비밀번호도 동일하게 설정

아래 파일의 비밀번호를 Sentinel HA 비밀번호와 동일하게 맞춥니다.

- `apps/valkey-cache-tester/k8s/base/secret.yaml`

예시:

```yaml
stringData:
  VALKEY_PASSWORD: 실제-비밀번호
```

## 5. Cache Tester 이미지 준비

이미지를 빌드하고 푸시합니다.

```powershell
$Image = "<registry>/valkey-cache-tester:0.1.0"

docker build -t $Image .\apps\valkey-cache-tester
docker push $Image
```

그 다음 아래 파일에서 이미지 값을 실제 경로로 수정합니다.

- `apps/valkey-cache-tester/k8s/base/deployment.yaml`

예시:

```yaml
image: <registry>/valkey-cache-tester:0.1.0
```

## 6. Sentinel HA 배포

현재 Sentinel 구성은 namespace `valkey-sentinel-ha`에 올라갑니다.

```powershell
kubectl apply -k .\deployments\sentinel-ha
```

배포 상태를 확인합니다.

```powershell
kubectl get pods -n valkey-sentinel-ha
kubectl get svc -n valkey-sentinel-ha
kubectl get pvc -n valkey-sentinel-ha
```

기대 상태:

- Valkey Pod 3개
- Sentinel Pod 3개
- 관련 서비스 생성
- PVC가 `Bound`

## 7. Cache Tester Sentinel overlay 배포

```powershell
kubectl apply -k .\apps\valkey-cache-tester\k8s\overlays\sentinel
```

확인:

```powershell
kubectl get pods -n valkey-sentinel-ha
kubectl get svc -n valkey-sentinel-ha
```

기대 상태:

- `valkey-cache-tester` Pod가 `Running`

## 8. 포트포워딩

별도 PowerShell 창에서 아래 명령을 실행하고 유지합니다.

```powershell
kubectl port-forward -n valkey-sentinel-ha svc/valkey-cache-tester 8080:8080
```

## 9. 테스트 변수 준비

다른 PowerShell 창에서 아래 변수를 준비합니다.

```powershell
$BaseUrl = "http://127.0.0.1:8080"
$Headers = @{
    "Content-Type" = "application/json"
}
```

## 10. Sentinel 연결 상태 확인

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/live"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/connection-info"
```

기대 결과:

- `mode`가 `sentinel`
- Sentinel endpoint 정보가 보임
- write/read ping이 성공

## 11. 데이터 쓰기

```powershell
$Body = @{
    key = "demo-sentinel"
    value = @{
        message = "hello"
        source = "sentinel"
    }
    ttl_seconds = 300
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/items" -Headers $Headers -Body $Body
```

## 12. write/read 조회

write 경로:

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-sentinel?source=write"
```

read 경로:

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-sentinel?source=read"
```

기대 결과:

- write는 Sentinel이 찾은 현재 primary로 접근
- read는 Sentinel이 찾은 replica 경로로 접근

## 13. roundtrip 테스트

```powershell
$RoundTripBody = @{
    ttl_seconds = 120
    read_attempts = 5
    read_delay_ms = 200
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/roundtrip" -Headers $Headers -Body $RoundTripBody
```

기대 결과:

- `replica_visible = true`

## 14. Sentinel 상태 직접 확인

Sentinel master 정보 확인:

```powershell
kubectl exec -n valkey-sentinel-ha valkey-sentinel-0 -- `
  valkey-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
```

Valkey 역할 확인:

```powershell
kubectl exec -n valkey-sentinel-ha valkey-0 -- valkey-cli -a <비밀번호> ROLE
kubectl exec -n valkey-sentinel-ha valkey-1 -- valkey-cli -a <비밀번호> ROLE
kubectl exec -n valkey-sentinel-ha valkey-2 -- valkey-cli -a <비밀번호> ROLE
```

기대 결과:

- 1개는 `master`
- 나머지는 `slave`

## 15. 장애 테스트 상세 가이드

이 섹션은 실제 테스트 결과를 기록하지 않습니다. 대신 각 장애 시나리오에서 정상적으로 보이면 어떤 현상이 나타나야 하는지만 정리합니다.

### 15-1. 현재 primary 식별

먼저 현재 primary와 replica를 확실히 구분합니다.

```powershell
kubectl exec -n valkey-sentinel-ha valkey-sentinel-0 -- `
  valkey-cli -p 26379 SENTINEL get-master-addr-by-name mymaster

kubectl exec -n valkey-sentinel-ha valkey-0 -- valkey-cli -a <비밀번호> ROLE
kubectl exec -n valkey-sentinel-ha valkey-1 -- valkey-cli -a <비밀번호> ROLE
kubectl exec -n valkey-sentinel-ha valkey-2 -- valkey-cli -a <비밀번호> ROLE
```

정상적으로 보면:

- Sentinel이 반환한 master 주소와 `ROLE` 결과의 `master` Pod가 일치해야 합니다.
- 나머지 두 Pod는 `slave`여야 합니다.

### 15-2. primary Pod 장애 테스트

1. 먼저 테스트 키를 하나 써 둡니다.
2. 현재 primary Pod를 찾습니다.
3. 그 Pod를 삭제합니다.
4. Sentinel이 새 primary를 선출하는지 확인합니다.
5. 앱 health와 read/write를 다시 호출합니다.

primary 삭제:

```powershell
kubectl delete pod -n valkey-sentinel-ha <현재-primary-pod명>
```

Sentinel 재확인:

```powershell
kubectl exec -n valkey-sentinel-ha valkey-sentinel-0 -- `
  valkey-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
```

앱 재확인:

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-sentinel?source=write"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-sentinel?source=read"
```

정상적으로 보면:

- Sentinel이 알려주는 master 주소가 기존 primary에서 다른 Pod로 바뀌어야 합니다.
- 살아 있던 replica 중 하나가 `master`로 승격되어야 합니다.
- 삭제됐던 기존 primary Pod가 다시 떠도 곧바로 `master`가 아니라 `slave`로 합류해야 합니다.
- 앱의 `/health/ready`는 잠깐 흔들릴 수 있지만 결국 다시 성공 상태로 돌아와야 합니다.
- write 요청은 새 primary로 성공해야 하고, read 요청도 replica 경로에서 다시 성공해야 합니다.

### 15-3. replica Pod 장애 테스트

현재 replica 중 하나를 삭제합니다.

```powershell
kubectl delete pod -n valkey-sentinel-ha <현재-replica-pod명>
```

재확인:

```powershell
kubectl get pods -n valkey-sentinel-ha
kubectl exec -n valkey-sentinel-ha valkey-sentinel-0 -- `
  valkey-cli -p 26379 SENTINEL replicas mymaster
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
```

정상적으로 보면:

- 현재 primary는 바뀌지 않아야 합니다.
- write 요청은 계속 성공해야 합니다.
- read 요청은 남아 있는 replica가 있으면 계속 성공할 수 있습니다.
- 삭제한 replica Pod가 다시 뜨면 Sentinel이 replica 목록에 다시 포함해야 합니다.

### 15-4. Sentinel Pod 1개 장애 테스트

Sentinel Pod 하나만 삭제합니다.

```powershell
kubectl delete pod -n valkey-sentinel-ha valkey-sentinel-0
```

정상적으로 보면:

- 남은 Sentinel 2개가 quorum을 유지하므로 감시 기능은 계속 살아 있어야 합니다.
- 현재 primary가 정상일 때 앱 read/write는 영향 없이 동작해야 합니다.
- 삭제한 Sentinel Pod가 다시 올라오면 quorum 3개 구성이 복구되어야 합니다.

### 15-5. Sentinel quorum 부족 테스트

Sentinel 2개를 내린 뒤 primary 장애를 유도하는 시나리오입니다.

```powershell
kubectl delete pod -n valkey-sentinel-ha valkey-sentinel-0
kubectl delete pod -n valkey-sentinel-ha valkey-sentinel-1
kubectl delete pod -n valkey-sentinel-ha <현재-primary-pod명>
```

정상적으로 보면:

- Sentinel quorum이 부족하면 자동 failover가 진행되지 않는 것이 정상입니다.
- 즉, 새 primary가 바로 선출되지 않을 수 있습니다.
- 이 상황에서는 앱 write 요청이 실패하거나 `/health/ready`가 실패할 수 있습니다.
- Sentinel 3개 구성이 다시 복구된 뒤에만 정상적인 failover 판단이 가능해집니다.

### 15-6. 복구 후 최종 확인

장애 테스트가 끝난 뒤 아래를 확인합니다.

```powershell
kubectl get pods -n valkey-sentinel-ha
kubectl exec -n valkey-sentinel-ha valkey-sentinel-0 -- `
  valkey-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
```

정상적으로 보면:

- Valkey 3개, Sentinel 3개가 다시 모두 Running 상태여야 합니다.
- Sentinel이 현재 master를 정상적으로 반환해야 합니다.
- 앱 health/read/write가 다시 안정적으로 성공해야 합니다.

## 16. 정리

Sentinel 환경 삭제:

```powershell
kubectl delete -k .\apps\valkey-cache-tester\k8s\overlays\sentinel --ignore-not-found
kubectl delete -k .\deployments\sentinel-ha --ignore-not-found
```

PVC까지 지우고 싶으면:

```powershell
kubectl delete pvc --all -n valkey-sentinel-ha
```

## 17. 자주 보는 문제

`/health/ready` 실패:

- `deployments/sentinel-ha/secret.yaml`와 `apps/valkey-cache-tester/k8s/base/secret.yaml` 비밀번호가 다름
- Sentinel Pod가 아직 quorum 형성 전

write는 되는데 read가 실패:

- Sentinel이 replica를 아직 정상적으로 인식하지 못함
- replica Pod 상태가 비정상

failover가 안 보임:

- 실제 primary Pod가 아닌 replica Pod를 삭제했을 수 있음
- Sentinel quorum이 부족할 수 있음
