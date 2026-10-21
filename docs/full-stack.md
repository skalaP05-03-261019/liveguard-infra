> 이전 6서비스 검증 기록(2026-10-21 오전). 현재 실행·정책·Gateway·화면은 [최신 통합 문서](v1-integration.md)를 참조한다. 아래 당시 미구현 상태와 포트는 최신 완료 주장으로 사용하지 않는다.

# 로컬 전체 서비스 연결 — 2026-10-21

## 실제 확인한 범위

Frontend → nginx → Backend → PostgreSQL의 로그인·세션·CSRF·채팅·SSE를 실제 브라우저로 검증했습니다. 다른 시청자의 화면과 이력 API에 HELD 원문이 노출되지 않으며, 작성자와 담당 운영자는 조회할 수 있습니다. 브라우저 요청을 Mock으로 교체하지 않았습니다.

Agent·Business MCP·RAG MCP도 같은 Docker 네트워크에서 실행합니다. 실제 MCP 세션과 tools/list, Agent SDK → Business MCP → Backend context 호출을 검증했습니다. 이것은 AI 분석·운영자 승인까지 완료했다는 의미가 아닙니다.

| 저장소 | 검증 기준 |
| --- | --- |
| liveguard-be | main `45962f274cf250c60c668ab5b6f4f4ba1e075568` (검증 도중 PR #16 병합분을 추가 반영) |
| liveguard-fe | main `1a29dd6ea144ef9b4ba0f02d5e31ae400b296ce3` |
| liveguard-agent | [PR #32](https://github.com/skalaP05-03-261019/liveguard-agent/pull/32), `5f304d4` on `fix/business-mcp-compose-host`; runtime [PR #27](https://github.com/skalaP05-03-261019/liveguard-agent/pull/27) 위에 쌓음 |
| liveguard-infra | main/default `d2d350d1929810abfc6d9bfc7dc213f7f61f6679` + this branch |

Agent main에는 아직 runtime PR #27이 반영되지 않았습니다. 아래 브랜치는 runtime과 통합 수정이 포함된 검증 기준입니다. 팀 리뷰 전 main을 자동 머지하지 않습니다.

## 실행

네 저장소를 같은 상위 디렉터리에 둡니다. Agent는 `fix/business-mcp-compose-host` 브랜치를 사용합니다. BE·FE는 위 main 기준입니다. 기존 변경이 있는 체크아웃을 강제로 전환하지 않습니다.

```bash
cd liveguard-infra
python3 scripts/init-local-env.py
docker compose -p liveguard-connected -f compose.yaml -f compose.full.yaml config --quiet
docker compose -p liveguard-connected -f compose.yaml -f compose.full.yaml up -d --build
docker compose -p liveguard-connected -f compose.yaml -f compose.full.yaml ps
```

`init-local-env.py`는 새 `.env`에 독립적인 로컬 비밀번호/토큰을 생성하고 파일 권한을 0600으로 설정합니다. 기존 `.env`는 덮어쓰지 않습니다. 기존 파일이 있으면 `.env.example`의 누락 이름만 수동으로 추가합니다. DB URL에 들어가는 비밀번호에는 URL 인코딩이 필요하므로 생성기의 hex 값을 권장합니다. `config --quiet`를 사용해 비밀값 전체 출력을 피합니다.

- 브라우저: **http://localhost:3000**
- 계정: `viewer`, `moderator`, `admin` / 로컬 시드 비밀번호 `liveguard-local`
- Backend: http://localhost:8080
- Agent health: http://localhost:8001/health
- DB: localhost:5433
- MCP는 호스트 포트를 열지 않고 Docker 네트워크에서만 접근합니다.

Frontend의 `VITE_USE_API=true`를 빌드에 고정하고 API 주소는 비워 같은 출처를 사용합니다. nginx의 `BACKEND_URL=http://backend:8080`이 세션 쿠키·CSRF·SSE를 전달합니다. 브라우저 코드는 Agent/MCP 비밀 토큰을 받지 않습니다. HTTP 개발 주소는 `localhost`를 사용해야 `crypto.randomUUID()` 등 브라우저 보안 컨텍스트 API가 동작합니다. 원격 HTTP 호스트에는 HTTPS 구성이 필요합니다.

종료는 아래 명령을 사용하며 DB와 Agent 작업 볼륨은 보존됩니다.

```bash
docker compose -p liveguard-connected -f compose.yaml -f compose.full.yaml stop
```

## 검증 재현

브라우저 검증은 전용 로컬 DB에 테스트 시청자를 추가합니다. 운영 DB에 실행하지 않습니다.

```bash
docker compose -p liveguard-connected -f compose.yaml -f compose.full.yaml exec -T db \
  psql -U liveguard -d liveguard -v ON_ERROR_STOP=1 < scripts/seed-observer.sql
python3 -m venv .venv-smoke
.venv-smoke/bin/pip install playwright==1.58.0
.venv-smoke/bin/playwright install chromium
.venv-smoke/bin/python scripts/browser-smoke.py --base-url http://localhost:3000
```

스크립트는 실제 UI 로그인·전송, 다른 세션의 SSE 수신, 새로고침 후 저장 확인, CSRF 누락 403, HELD 격리, 관리자 인증, 로그아웃 세션 무효화를 확인합니다. 시드 계정 비밀번호를 변경한 경우 `SMOKE_LOCAL_PASSWORD`로 전달합니다. DB 이름/사용자를 바꾼 경우 위 psql 인자도 조정합니다.

MCP/내부 API 검증은 이 디렉터리에서 실행합니다.

```bash
docker run --rm --network liveguard-connected_default -e PYTHONPATH=/app \
  --env-file .env -v "$PWD:/integration" \
  liveguard-agent:integration python /integration/scripts/service-smoke.py
```

이 검증은 현재 미구현 경계의 501/503도 명시적으로 확인하는 기준선입니다. Backend가 구현되면 성공 경로 검증으로 교체해야 합니다. 모델 호출과 실제 제재는 실행하지 않습니다.

결과: [브라우저 결과](../evidence/browser/result.json), [서비스 결과](../evidence/services.json), [Agent 회귀 테스트](../evidence/agent-regression.json). 실제 브라우저 검증 9개와 서비스 검증 8개를 통과했습니다. 결과는 `PASS_WITH_BACKEND_BLOCKERS`로 기록하며 전체 E2E 성공으로 표시하지 않습니다. 화면 캡처도 `evidence/browser`에 있습니다. Docker 안에서 브라우저가 nginx 컨테이너의 network namespace를 공유해 접근했으므로 캡처 결과 주소는 `localhost:8080`이며 호스트 접속 주소는 `localhost:3000`입니다.

## 전체 AI 관제 연결에 남은 사항

| 경계 | 현재 관찰 | 다음 구현 |
| --- | --- | --- |
| BE 후보 → 사건/작업 | `InMemoryCandidateSink`가 임시 caseId만 반환 | B2 사건·snapshot·evidenceVersion·실제 liveId 저장, 트랜잭션 커밋 후 Agent 작업 발송/재시도 |
| Agent 사건 조회 | `GET /internal/cases/{id}` → 501 | 계약 DTO와 일치하는 실제 snapshot 조회 |
| 운영 콘솔 사건 목록 | `GET /api/cases?channelId=` → 404 | 목록/상세 및 권한·SSE 구현 |
| CONTEXT 검토 | 생성/결정/반영 HTTP Gateway 미구현 | AI 제안 보존 → 사람 결정 BE 저장 → 같은 thread 재개, snapshot/version 재검증 |
| KICK 검토/실행 | BE basis/실행은 501, Agent 명령 스키마는 이전 형식 | 최신 liveId·basisCaseIds·basisSnapshotId·validationRef 계약 정렬 후 검증; 승인 우회 금지 |
| PII·사용자 이력 | security-facts/user-history 501 | 출처가 확인된 사실과 확정 이력 제공, 기간 미확정 사항은 추정 금지 |
| 배포 Gateway | `AGENT_GATEWAY_FACTORY`가 비어 있음 | 위 HTTP API에 대한 실제 ModerationGateway 구현 이후 연결 |
| 정책 검색 | RAG 키/색인 없음, indexedPolicyVersions=[] | 활성 policyVersion 팀 확인 후 키를 서버에 설정하고 정책 색인; 지금은 자동 호출 안 함 |
| 시스템 운영자 지표 | 로그인만 실제 연결, 지표는 systemMock | 서버 집계 계약/구현 후 실제 지표로 전환 |

`AGENT_GATEWAY_FACTORY`를 가짜 구현으로 채우거나 `readyForTasks=true`로 속이지 않습니다. 현재 Agent는 `/health`에서 false, 인증된 작업 조회에서 503을 반환합니다. RAG도 색인이 없으면 준비 완료로 표시하지 않습니다. MCP 도구 목록을 조회한 것과 정책 검색 품질을 검증한 것은 구분합니다.

## 정책 충돌 보존

Frontend 문서/Mock과 BE의 일부 기존 문서는 24시간 강퇴·자동 문맥 판정 중심의 이전 기준을 담고 있습니다. 사용자 확인 최신 기준은 같은 liveId에서 24시간 동안 확정 사건 3건을 집계하되, KICK 효력은 해당 live 종료까지이며 CONTEXT의 모든 모델 판단은 사람 검토를 거칩니다. 연결 작업에서 이 충돌을 임의로 해소하거나 기존 동작을 조용히 변경하지 않았습니다. BE 계약과 실제 정책 확정, FE 문구/버튼/이벤트 정렬이 후속 E2E의 전제입니다. FLOOD 최초 확정 주체·TIMEOUT 기간·활성 정책 버전의 미확정 사항도 유지합니다.

추가 확인: 검증 도중 BE PR #16이 main에 병합됐습니다. MatchingTag 6종, filterVersion, FLOOD 후보 묶기/10초 경계 계약을 추가한 변경이며 그대로 fast-forward해 다시 연결했습니다. 이 PR의 `docs/erd.md`는 liveId·handlingRoute·policyVersion을 v0.5 이번 범위에 넣지 않는다고 명시합니다. 이는 Agent 쪽 사용자 확인 기준과의 **명시적인 범위 충돌**입니다. 채널 ID를 liveId로 대신 보내는 임시 연결을 만들지 않았으며, 실제 Gateway/변이 연결 전 팀 계약 정렬이 필요합니다.
