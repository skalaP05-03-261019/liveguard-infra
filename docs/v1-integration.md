# 실제 6서비스 통합 시험 (Infra #4)

기존 Infra PR #3의 MCP/Agent/볼륨 문서를 기반으로 FE와 포트·빌드 경로 설정을 추가했다. #2의 이전 6서비스 통합 PR은 별개로 남아 있으며 무리하게 병합해 서로 덮어쓰지 않는다.

## 활성화

4개 저장소를 형제 디렉터리로 배치하고 `.env.example`을 `.env`로 복사한다. 비밀 값은 커밋하지 않는다. 이 통합은 BE #29/Agent #48/FE #2의 PR 구현에 의존한다. BE 통합 PR이 Draft인 동안 main만 clone한 구성에서 완성된 v1을 기대하지 않는다.

시험을 명시적으로 선택할 때만 다음 값을 설정한다.

```
LIVEGUARD_POLICY_VERSION=v3.1
LIVEGUARD_TBD_FIXTURE_ENABLED=true
VITE_USE_LIVE_V1=true
AGENT_DELIVERY_ENABLED=true
AGENT_GATEWAY_FACTORY=app.integration.http_gateway:configured_gateway
MODEL_PROVIDER=openai
MODEL_NAME=gpt-5.4-mini
```

`LIVEGUARD_OPENAI_API_KEY`에 유효한 키를 지정한다. 호스트의 오래된 `OPENAI_API_KEY`가 Compose 파일을 덮어쓰는 문제를 피하도록 별도 변수 이름을 사용한다. MCP 토큰/내부 토큰과 Agent 서비스 토큰은 따로 지정한다. 정책 원문·색인은 정확히 v3.1이어야 하며 로컬 시험 버전 선택이 배포 승인은 아니다.

```
docker compose config --quiet
docker compose up -d --build
docker compose run --rm --no-deps rag-mcp python -m app.rag_mcp.index
```

색인 CLI는 Agent README의 현재 인자를 확인한다. 데모 시청자 추가는 새 로컬 시험 DB에서만 `scripts/seed-v1-viewers.sql`을 실행한다. 기존 개발 DB/볼륨 삭제는 필요하지 않다. 빌드 context와 호스트 포트는 `.env.example`의 선택 변수로 바꿀 수 있다.

## 이번 실제 실행

별도 프로젝트 `liveguard-v1`, FE localhost:3002, BE localhost:8082, Agent localhost:8004, DB localhost:55440을 사용했다. 기존 `liveguard-connected`와 볼륨은 건드리지 않았다. moderator/viewer/admin 및 demo-viewer-10..19는 로컬 시드 비밀번호 `liveguard-local`을 사용한다.

실제 Chromium의 독립 세션과 실제 BE/DB/Outbox/Agent/Business MCP/RAG MCP/OpenAI를 사용했다. 네트워크 mock/고정 판정 응답은 쓰지 않았다. `evidence/v1-browser-final/report.json`과 이름별 PNG가 관찰 증거다. 초기 실패 시도는 최종 PASS의 증거로 포함하지 않는다. 모델 응답 품질은 매번 달라질 수 있으며 실패를 숨기지 않는다.

## 브라우저 재실행

```
docker build -t liveguard-browser-test verification
docker run --rm --network container:LIVEGUARD_FRONTEND_CONTAINER \
  -e BASE_URL=http://localhost:8080 \
  -e ATTACK_ACCOUNT=demo-viewer-14 \
  -v "$PWD/scripts:/scripts:ro" -v "$PWD/evidence:/evidence" \
  liveguard-browser-test
```

테스트는 정상/의심 채팅과 사람 결정을 실제 저장하므로 별도 로컬 DB에서 실행한다. ATTACK_ACCOUNT는 이전 실행에서 제한되지 않은 시청자 계정을 선택한다. 기본값은 demo-viewer-12다. `RUN_KICK=1`은 demo-viewer-13으로 별도 세 사건을 만든 뒤 강퇴 승인을 추가 시험한다. 이는 단순 조회 점검이 아니다. 생성한 브라우저는 테스트 종료 시 닫는다.

## 남은 범위

기본 v1 계약 전체 응답/페이지네이션·내부 확장 합의, PII 검증 사실, FLOOD 최초 확정, finding 취소/제재 복구 및 미정 정책의 팀 확정은 BE 통합 PR의 잔여 항목이다. 관찰 증거가 전체 서비스 운영 완성을 의미하지 않는다.

## 최종 실행 결과

재현용 `verification/Dockerfile`로 직접 빌드한 Chromium 이미지에서 최종 8개 시나리오가 모두 PASS했다. 캡처 10장, page error 0, mockedRequests 0이다. 별도 확정 사건 3건→별도 사람 KICK 승인→실제 Business MCP execute→대상 SSE 차단까지 관찰했다. BE 실행 기준은 `31aac95`, FE `6167361`, Agent `036d1f1`(이후 PR #50 병합)이다. BE 후속 익명 별칭 개선 `1ee726f`는 관련 Postgres 통합 테스트 8개를 별도로 통과했다.
