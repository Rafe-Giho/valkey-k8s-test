# 현재 Replication 배포 기준 Valkey Cache Tester 가이드

이 가이드는 현재 Valkey가 아래 파일들로 배포되어 있다고 가정합니다.

- `nks-csi-storageclass.yaml`
- `valkey-auth-secret.yaml`
- `valkey-values-nks.yaml`

또한 현재 Valkey 구성은 아래와 같다고 가정합니다.

- namespace: `valkey`
- 쓰기 서비스: `valkey`
- 읽기 서비스: `valkey-read`
- 인증 사용자: `default`

캐시 테스트 앱은 아래 overlay로 배포합니다.

- `valkey-cache-tester/k8s/overlays/replication`

## 1. 테스트 앱 이미지 수정

먼저 이미지를 빌드하고 레지스트리에 푸시합니다.

```powershell
docker build -t <registry>/valkey-cache-tester:0.1.0 .\valkey-cache-tester
docker push <registry>/valkey-cache-tester:0.1.0
```

그 다음 아래 파일에서 이미지를 실제 경로로 바꿉니다.

- `valkey-cache-tester/k8s/base/deployment.yaml`

이 값을:

```yaml
image: ghcr.io/replace-me/valkey-cache-tester:0.1.0
```

실제 사용하는 이미지 경로로 변경합니다.

## 2. Valkey 비밀번호와 동일하게 설정

아래 파일을 수정합니다.

- `valkey-cache-tester/k8s/base/secret.yaml`

여기의 `VALKEY_PASSWORD`를 아래 파일에 들어간 비밀번호와 동일하게 맞춥니다.

- `valkey-auth-secret.yaml`

예시:

```yaml
stringData:
  VALKEY_PASSWORD: 실제-비밀번호
```

## 3. 캐시 테스트 앱 배포

replication overlay를 적용합니다.

```powershell
kubectl apply -k .\valkey-cache-tester\k8s\overlays\replication
```

Pod와 Service를 확인합니다.

```powershell
kubectl get pods -n valkey
kubectl get svc -n valkey
```

기대 상태:

- `valkey-cache-tester` Pod가 `Running`
- 기존 `valkey`, `valkey-read` 서비스가 존재

## 4. 테스트 앱 포트포워딩

```powershell
kubectl port-forward -n valkey svc/valkey-cache-tester 8080:8080
```

이 터미널은 계속 열어둡니다.

## 5. 상태 확인

다른 터미널에서 아래 명령을 실행합니다.

```powershell
curl.exe http://127.0.0.1:8080/health/live
curl.exe http://127.0.0.1:8080/health/ready
curl.exe http://127.0.0.1:8080/connection-info
```

기대 결과:

- `/health/live`는 `ok` 반환
- `/health/ready`는 write/read ping 성공 정보 반환
- `/connection-info`는 `standalone` 모드와 `valkey`, `valkey-read` 정보를 보여줌

## 6. 테스트 데이터 쓰기

```powershell
curl.exe -X POST http://127.0.0.1:8080/cache/items ^
  -H "Content-Type: application/json" ^
  -d "{\"key\":\"demo\",\"value\":{\"message\":\"hello\"},\"ttl_seconds\":300}"
```

기대 결과:

- 응답에 `exists: true`
- 응답 source는 `write`

## 7. write 경로에서 조회

```powershell
curl.exe "http://127.0.0.1:8080/cache/items/demo?source=write"
```

기대 결과:

- primary 경로에서 즉시 데이터 조회

## 8. read 경로에서 조회

```powershell
curl.exe "http://127.0.0.1:8080/cache/items/demo?source=read"
```

기대 결과:

- read 서비스 경로에서도 동일한 데이터 조회
- 즉, 앱 기준으로 replica 쪽에서도 값이 보인다는 뜻

## 9. roundtrip 테스트

```powershell
curl.exe -X POST http://127.0.0.1:8080/cache/roundtrip ^
  -H "Content-Type: application/json" ^
  -d "{\"ttl_seconds\":120,\"read_attempts\":5,\"read_delay_ms\":200}"
```

기대 결과:

- `write.exists`가 `true`
- `read.exists`가 `true`
- `replica_visible`이 `true`

만약 `replica_visible`이 `false`이면 복제 상태나 read 서비스 라우팅을 확인해야 합니다.

## 10. 샘플 데이터 적재

```powershell
curl.exe -X POST http://127.0.0.1:8080/cache/seed ^
  -H "Content-Type: application/json" ^
  -d "{\"prefix\":\"sample\",\"count\":5,\"ttl_seconds\":300}"
```

기대 결과:

- 샘플 키들이 정상적으로 저장됨

## 11. 테스트 데이터 삭제

```powershell
curl.exe -X DELETE http://127.0.0.1:8080/cache/items/demo
```

## 12. 장애 확인 및 문제 해결

앱 로그 확인:

```powershell
kubectl logs -n valkey deploy/valkey-cache-tester
```

Pod 내부 환경변수 확인:

```powershell
kubectl exec -n valkey deploy/valkey-cache-tester -- printenv | findstr VALKEY
```

자주 보는 문제:

- `/health/ready` 실패
  - `valkey-cache-tester/k8s/base/secret.yaml`의 비밀번호가 틀림
  - Valkey 서비스가 아직 준비되지 않음
- write는 되는데 read가 실패
  - `valkey-read` 서비스가 없음
  - replica Pod 상태가 비정상
- Pod가 시작되지 않음
  - `deployment.yaml`의 이미지 경로가 잘못됨
  - 이미지 pull 권한이 없음
