# Sentinel 버전 전환 및 PowerShell 테스트 가이드

이 문서는 현재 아래 파일들로 배포된 Helm 기반 replication 환경을 내리고:

- `nks-csi-storageclass.yaml`
- `valkey-auth-secret.yaml`
- `valkey-values-nks.yaml`

새로 만든 Sentinel HA 구성으로 전환한 뒤, `valkey-cache-tester`로 테스트하는 과정을 PowerShell 기준으로 설명합니다.

이 가이드의 대상 파일:

- Valkey Sentinel HA: `k8s/valkey-sentinel-ha`
- Cache Tester Sentinel overlay: `valkey-cache-tester/k8s/overlays/sentinel`

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

- `k8s/valkey-sentinel-ha/secret.yaml`

예시:

```yaml
stringData:
  password: 실제-비밀번호
```

## 4. Cache Tester 비밀번호도 동일하게 설정

아래 파일의 비밀번호를 Sentinel HA 비밀번호와 동일하게 맞춥니다.

- `valkey-cache-tester/k8s/base/secret.yaml`

예시:

```yaml
stringData:
  VALKEY_PASSWORD: 실제-비밀번호
```

## 5. Cache Tester 이미지 준비

이미지를 빌드하고 푸시합니다.

```powershell
$Image = "<registry>/valkey-cache-tester:0.1.0"

docker build -t $Image .\valkey-cache-tester
docker push $Image
```

그 다음 아래 파일에서 이미지 값을 실제 경로로 수정합니다.

- `valkey-cache-tester/k8s/base/deployment.yaml`

예시:

```yaml
image: <registry>/valkey-cache-tester:0.1.0
```

## 6. Sentinel HA 배포

현재 Sentinel 구성은 namespace `valkey-sentinel-ha`에 올라갑니다.

```powershell
kubectl apply -k .\k8s\valkey-sentinel-ha
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
kubectl apply -k .\valkey-cache-tester\k8s\overlays\sentinel
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

## 15. 장애 테스트 예시

현재 primary가 어떤 Pod인지 먼저 ROLE로 확인합니다.

그 다음 현재 primary Pod를 삭제합니다.

```powershell
kubectl delete pod -n valkey-sentinel-ha <현재-primary-pod명>
```

잠시 후 Sentinel이 새 primary를 선출하는지 확인합니다.

```powershell
kubectl exec -n valkey-sentinel-ha valkey-sentinel-0 -- `
  valkey-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
```

그 뒤 다시 앱 헬스체크와 조회 테스트를 수행합니다.

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-sentinel?source=write"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo-sentinel?source=read"
```

## 16. 정리

Sentinel 환경 삭제:

```powershell
kubectl delete -k .\valkey-cache-tester\k8s\overlays\sentinel --ignore-not-found
kubectl delete -k .\k8s\valkey-sentinel-ha --ignore-not-found
```

PVC까지 지우고 싶으면:

```powershell
kubectl delete pvc --all -n valkey-sentinel-ha
```

## 17. 자주 보는 문제

`/health/ready` 실패:

- `k8s/valkey-sentinel-ha/secret.yaml`와 `valkey-cache-tester/k8s/base/secret.yaml` 비밀번호가 다름
- Sentinel Pod가 아직 quorum 형성 전

write는 되는데 read가 실패:

- Sentinel이 replica를 아직 정상적으로 인식하지 못함
- replica Pod 상태가 비정상

failover가 안 보임:

- 실제 primary Pod가 아닌 replica Pod를 삭제했을 수 있음
- Sentinel quorum이 부족할 수 있음
