# 현재 Replication 배포 기준 PowerShell 전용 테스트 가이드

이 문서는 현재 아래 파일들로 배포된 Valkey 환경을 기준으로 합니다.

- `nks-csi-storageclass.yaml`
- `valkey-auth-secret.yaml`
- `valkey-values-nks.yaml`

가정하는 현재 구성:

- namespace: `valkey`
- write 서비스: `valkey`
- read 서비스: `valkey-read`
- 테스트 앱 overlay: `valkey-cache-tester/k8s/overlays/replication`

이 가이드는 PowerShell 기준으로 바로 실행할 수 있게 작성했습니다.

## 1. 작업 폴더 이동

```powershell
Set-Location c:\Users\user\Desktop\신기호\업무용\30.PoC\valkey
```

## 2. 테스트 앱 이미지 빌드 및 푸시

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

## 3. 테스트 앱 비밀번호 설정

아래 파일을 수정합니다.

- `valkey-cache-tester/k8s/base/secret.yaml`

여기의 `VALKEY_PASSWORD`는 현재 Valkey에 적용된 비밀번호와 같아야 합니다.

기준 파일:

- `valkey-auth-secret.yaml`

## 4. 테스트 앱 배포

```powershell
kubectl apply -k .\valkey-cache-tester\k8s\overlays\replication
kubectl get pods -n valkey
kubectl get svc -n valkey
```

기대 상태:

- `valkey-cache-tester` Pod가 `Running`
- `valkey`, `valkey-read`, `valkey-cache-tester` 서비스가 보임

## 5. 포트포워딩

별도 PowerShell 창에서 아래 명령을 실행하고 그대로 유지합니다.

```powershell
kubectl port-forward -n valkey svc/valkey-cache-tester 8080:8080
```

## 6. 테스트용 변수 준비

다른 PowerShell 창에서 아래 변수들을 먼저 잡습니다.

```powershell
$BaseUrl = "http://127.0.0.1:8080"
$Headers = @{
    "Content-Type" = "application/json"
}
```

## 7. 헬스체크

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/live"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/ready"
Invoke-RestMethod -Method Get -Uri "$BaseUrl/connection-info"
```

기대 결과:

- `live`는 `ok`
- `ready`는 write/read ping 결과 반환
- `connection-info`는 `standalone` 모드와 `valkey`, `valkey-read` 대상 정보 반환

## 8. 캐시 데이터 쓰기

```powershell
$Body = @{
    key = "demo"
    value = @{
        message = "hello"
        source = "powershell"
    }
    ttl_seconds = 300
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/items" -Headers $Headers -Body $Body
```

기대 결과:

- `exists = true`
- `source = write`

## 9. write 경로 조회

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo?source=write"
```

## 10. read 경로 조회

```powershell
Invoke-RestMethod -Method Get -Uri "$BaseUrl/cache/items/demo?source=read"
```

기대 결과:

- write와 read 양쪽 모두 같은 payload가 보여야 함

## 11. roundtrip 테스트

```powershell
$RoundTripBody = @{
    ttl_seconds = 120
    read_attempts = 5
    read_delay_ms = 200
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/roundtrip" -Headers $Headers -Body $RoundTripBody
```

기대 결과:

- `write.exists = true`
- `read.exists = true`
- `replica_visible = true`

## 12. 샘플 데이터 적재

```powershell
$SeedBody = @{
    prefix = "sample"
    count = 5
    ttl_seconds = 300
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$BaseUrl/cache/seed" -Headers $Headers -Body $SeedBody
```

## 13. 테스트 데이터 삭제

```powershell
Invoke-RestMethod -Method Delete -Uri "$BaseUrl/cache/items/demo"
```

## 14. 로그 및 환경변수 확인

앱 로그:

```powershell
kubectl logs -n valkey deploy/valkey-cache-tester
```

앱 Pod 내부 환경변수:

```powershell
kubectl exec -n valkey deploy/valkey-cache-tester -- printenv
```

Valkey 관련 변수만 보고 싶으면:

```powershell
kubectl exec -n valkey deploy/valkey-cache-tester -- printenv | Select-String VALKEY
```

## 15. 자주 보는 문제

`/health/ready` 실패:

- `valkey-cache-tester/k8s/base/secret.yaml`의 비밀번호가 현재 Valkey 비밀번호와 다름
- `valkey` 또는 `valkey-read` 서비스가 준비되지 않음

write는 되는데 read가 실패:

- `valkey-read` 서비스가 없음
- replica Pod 상태가 비정상

Pod가 안 뜸:

- `deployment.yaml`의 이미지 경로가 잘못됨
- 레지스트리 pull 권한이 없음
