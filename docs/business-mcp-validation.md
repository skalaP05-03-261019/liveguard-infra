# Business MCP HA 검증 기록 (2026-10-23)

## 실행 기준

- Infra main `abf54b11998ad1abbc05022ab190c348328eff8f`에서 분기.
- Agent main `764eab26a8272d72fc79bcad5b6e7aa82ef8d8b0` (#95 merge).
- Docker Engine 29.6.1 / arm64. 실제 실행한 이미지 버전/ID는 운영 문서 참조.
- 기존 운영 stack에는 적용하지 않았다. 새 프로젝트에서 production Compose에 테스트용
  fixture override를 적용했다. 실제 `.env`는 읽기 전용으로 사용하고 출력/수정하지 않았다.

## 결과

| 항목 | 결과 | 근거 및 한계 |
|---|---|---|
| Compose config --quiet | PASS | 임시 project 생성 전 실행 |
| 기존 서비스 정규화 비교 | PASS | db/backend/rag/frontend/rabbit 동일, Agent 제한값 2개만 추가 |
| HAProxy 문법 | PASS | pinned image의 `haproxy -c -f` exit 0; 독립 검사에서는 DNS 미존재 notice 가능 |
| 실제 health 도구 | PASS | MCP Python urllib, HAProxy BusyBox wget 실행 확인 |
| 두 MCP image ID | PASS | 양쪽 동일한 로컬 image ID 기록 |
| 정상 인증 조회 분산 | PASS | 가상 Backend 관측 source IP, 두 MCP 각각 6건 |
| MCP1 SIGKILL | PASS | probe 수렴 뒤 MCP2가 신규 조회 12건 전부 처리 |
| 의존성을 적용한 최초 시작 | PASS | MCP1 실행 중이나 unavailable, `--no-deps` 없이 Agent→LB→MCP 시작, MCP2 조회 12건 |
| MCP 자동 재시작 | PASS | 실제 unless-stopped 상태 내부 SIGTERM 후 restart count 증가 및 양쪽 조회 |
| unavailable 상태 재생성 | PASS | MCP1 중지 상태에서 `--no-deps`로 LB와 Agent 재생성, MCP2 조회 12건; 초기 시작 시험과 별도 |
| IP 변경 후 복구 | PASS | 재생성 전 IP와 다른 IP 확인 후 두 MCP 각각 6건 |
| 진행 요청 graceful 종료 | PASS | 요청 처리 중 stop, 1초 뒤 요청/stop 미완료, release 후 정상 응답, 생존 MCP 조회 12건 |
| drain /ready 503 외부 관측 | NOT RUN | Docker shutdown 중 listener 종료가 빠름; 503 자체는 아래 app test로 검증 |
| ready/drain/용량/deadline | PASS | Agent 기존 test_business_mcp_cluster 10개 통과 |
| 전체 MCP 중지 | PASS | 공통 LB /ready에서 HTTP 503 |
| 자동 재전송 없음 | PASS | HAProxy retries 0 확인, Agent 기존 mutation response-loss 테스트 통과; 실제 Spring 변경 효과는 별도 |
| 실제 Spring 인증 조회 | PASS | 기존 final-review Spring Backend에 공통 LB를 통한 get_moderation_case 4회 성공, body 미출력 |
| 실제 Spring 양쪽 처리 식별 | NOT RUN | Spring 진단 계측을 변경하지 않음; 양쪽 처리 증거는 가상 Backend에서 확보 |
| 토큰 로그 노출 검사 | PASS | MCP/LB 로그에 사용한 기존 두 토큰 미포함; 본문 로그 미활성 |
| 기존 mount 전후 비교 | PASS | 기존 LIVE:GUARD 네 프로젝트 컨테이너 mount 동일, 테스트에 기존 볼륨 마운트 없음 |
| 운영 stack 적용/롤백 실행 | NOT RUN | 운영 컨테이너 변경 없이 문서 제공 |
| 실제 Spring UNKNOWN/execute 1회/효과 1회 | NOT RUN | BE·Agent 공동 인수 필요 |
| 다중 Agent 통합 | NOT RUN | 요청 범위 밖 |

시험은 정확한 6:6 비율을 강제하지 않고 두 IP가 실제 조회를 처리했는지만 검증한다.
장애 직후 수렴 전에 발생 가능한 실패를 숨기기 위한 client 재시도는 넣지 않았다.
초기 검증 실행은 전체 호스트 컨테이너를 비교하던 보존 assertion에서 실패했다.
보존 대상을 기존 LIVE:GUARD 프로젝트로 명시하도록 수정하고 재실행했다.
실패한 최초 실행을 PASS로 집계하지 않는다.

## 실행 명령

```bash
# 환경별 기존 .env 경로 및 build context를 명시. 토큰은 셸 명령에 직접 넣지 않음.
export BUSINESS_MCP_IMAGE=liveguard-business-mcp:764eab26a827
export AGENT_BUILD_CONTEXT=/absolute/path/to/agent-at-764eab26a827
export BACKEND_BUILD_CONTEXT=/absolute/path/to/liveguard-be
export FRONTEND_BUILD_CONTEXT=/absolute/path/to/liveguard-fe
docker build -t "$BUSINESS_MCP_IMAGE" "$AGENT_BUILD_CONTEXT"
python3 scripts/verify-business-mcp-config.py --env-file /safe/existing/.env \
  --project liveguard-infra --output evidence/business-mcp-ha.json
python3 scripts/verify-business-mcp.py --env-file /safe/existing/.env \
  --preserve-project liveguard-infra --preserve-project liveguard-final-review --preserve-project liveguard-main-review \
  --preserve-project liveguard-v1-review --output evidence/business-mcp-ha.json
docker run --rm -v "$PWD/haproxy/business-mcp.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro" \
  haproxy:3.0.30-alpine@sha256:cf3af0facf7eb22b9fee463daf0fbc07ead740b8150696dce724264faf7b4318 \
  haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
docker run --rm -v "$AGENT_BUILD_CONTEXT/tests:/tests:ro" -e PYTHONPATH=/tests \
  "$BUSINESS_MCP_IMAGE" python -m unittest test_business_mcp_cluster -q
# 실제 출력: Ran 10 tests ... OK
git diff --check
```

Spring 시험은 별도 `liveguard-mcp-spring-check` 프로젝트의 두 MCP와 HAProxy만 실행했다.
Backend URL만 `http://host.docker.internal:8084`로 override하고 기존
`liveguard-final-review-backend-1`의 서비스 토큰을 메모리 내에서 전달했다.
기존 DB `guard.cases`에서 한 case ID를 read-only SELECT하여 Agent SDK의
`get_moderation_case`를 4회 호출했다. 응답 본문·도구 인자·토큰은 출력하지 않았다.
변경 도구나 DB 쓰기는 실행하지 않았다. 시험 컨테이너/네트워크는 제거했다.

## 완료 범위

보완 후 Docker 가용성·정적 검증을 재실행했다. Spring 인증 조회 4회 성공은 최초 구현 때의
관측이며 이번 보완에서는 재실행하지 않았다. 중복 Spring JSON은 제거하고 이 기록을 유지한다.
운영 배포, 실제 종료 순간의 HTTP 503 포착, 실제 Spring 변경 효과 공동 인수는 미완료다.
이미지 재빌드 재현성, 운영 부하, 네트워크 분할, 전체 Agent 업무 readiness까지 검증한
결과로 확대 해석하지 않는다. 최종 운영 인수는 위 미완료 항목을 확인한 후 진행한다.


## 병합 전 보완

- 실제 Agent 소스 커밋 및 clean checkout 검증을 배포 전 필수 단계로 추가했다.
- 신규 MCP 두 대의 readiness와 실제 Backend 인증 조회가 성공한 경우에만 기존 MCP를 교체한다.
- 보호 대상이 없으면 NOT RUN, 명시한 프로젝트가 없으면 실패한다. 증거에는 비교 개수만 남긴다.
- JSON 세 개를 하나로 통합했다. 상세 Docker mount 내부 경로 대신 비교 상태·대상 개수를 기록한다.
- GitHub Actions는 비밀정보 없이 Compose·HAProxy·Python 정적 검증을 수행한다.
  portable 모드에서는 역사적 서비스 비교·소스 provenance·build 경로 확인을 NOT RUN으로 구분한다.
  기존 서비스의 정상적인 후속 변경을 막지 않도록 CI에서는 과거 커밋과 비교하지 않는다.

보완 중 자동 재시작 시험은 Docker API 수동 kill을 사용해 timeout으로 실패했다.
컨테이너 내부 SIGTERM으로 프로세스가 종료되는 상황으로 수정하여 재실행했다.
mount 반환 순서가 달라 동일 구성을 실패로 판정한 것도 확인하여 destination 기준 정렬 후 비교한다.
