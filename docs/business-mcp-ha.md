# Business MCP 이중화 운영 및 검증

관련: [Agent #94](https://github.com/skalaP05-03-261019/liveguard-agent/issues/94),
[Agent #95](https://github.com/skalaP05-03-261019/liveguard-agent/pull/95).
이 변경은 단일 Agent의 Business MCP 호출 분산이다. 다중 Agent 통합 완료가 아니다.

## 기준과 변경 범위

2026-10-23 원격 Infra main `abf54b11998ad1abbc05022ab190c348328eff8f`,
Agent main `764eab26a8272d72fc79bcad5b6e7aa82ef8d8b0` 기준이다.
참고 Agent Compose의 두 upstream `service_healthy` 의존성을 그대로 복사하지 않았다.
LB는 `service_started`만 요구하며 한 upstream 프로세스가 준비되지 않아도 시작한다.
컨테이너 자체를 생성할 수 없는 이미지/엔진 오류는 일반적인 Compose 시작 실패이며,
이미지 준비 후 `up --no-deps business-mcp agent`로 정상 upstream을 이용할 수 있다.

```text
변경 전: Agent → business-mcp (Python MCP) → Backend
변경 후: Agent → business-mcp (HAProxy) → business-mcp-1/2 → Backend
공통 URL: http://business-mcp:8002/mcp (불변)
```

기존 db/backend/rag-mcp/frontend/rabbitmq 및 rabbit profile, 호스트 포트,
build context 기본값, 네트워크, Agent SQLite/Checkpointer 설정은 유지한다.
Agent에는 concurrency 8, deadline 10초만 추가했다. 기존 Agent 구현이 슬롯 대기,
초기화/schema 조회/도구 호출/정리를 하나의 timeout 안에 포함하므로 중복 구현하지 않는다.
stateless HTTP MCP만 지원하며 sticky session, 공유 MCP session DB를 추가하지 않는다.
HAProxy 요청별 roundrobin, retries 0; 실패 요청의 자동 재전송은 없다.

## 이미지와 환경변수

- HAProxy: `haproxy:3.0.30-alpine@sha256:cf3af0facf7eb22b9fee463daf0fbc07ead740b8150696dce724264faf7b4318`.
  실제 pull 및 `haproxy -v`에서 3.0.30 확인, arm64 Docker Engine 29.6.1에서 검증.
- MCP: `liveguard-business-mcp:764eab26a827`, 위 Agent 커밋의 공용 Dockerfile에서 한 번 빌드.
  검증한 로컬 image ID: `sha256:1b8b0c754dc3876d6374a708cb055215166cab4b78c3d17ccd88b606ba30564c`.
  이는 로컬 빌드 ID이며 registry pull digest가 아니다. 재빌드는 base image 때문에
  다른 ID를 만들 수 있다. 두 서비스의 실제 `.Image`가 동일한지 매 배포 확인한다.
  임의 태그 재사용 대신 소스 커밋별 새 태그를 사용한다.
- `BUSINESS_MCP_IMAGE`는 필수. `pull_policy: never`로 사전에 빌드/반입한 동일 이미지를 사용한다.
  registry 배포는 digest 지정 후 명시적으로 pull하고 시작한다.
- `AGENT_BUILD_CONTEXT`는 위 커밋의 Agent checkout 경로. 기존 오래된 checkout을
  버전 이름만 바꿔 빌드하지 않는다. 아래 정적 검증은 커밋 불일치나 tracked/untracked 변경이 있으면 중단한다. Agent 제한값을 적용하려면 Agent 이미지도 해당 구현 필요.
- `BACKEND_BUILD_CONTEXT`, `FRONTEND_BUILD_CONTEXT` 기본 형제 저장소 경로 유지.
- 인증: 기존 `INTERNAL_SERVICE_TOKEN`, `BUSINESS_MCP_AGENT_TOKEN` 유지. 임의 재발급 금지.
- MCP 요청/pool 16, Backend timeout 10초, MCP shutdown 20초, Compose grace 30초.
- Agent concurrency 8, 전체 deadline 10초. `.env.example`에 설정 항목을 제공한다.

## 적용 전 보존 확인과 초기 적용

운영 변경은 이번 작업에서 실행하지 않았다. 기존 프로젝트 디렉터리와 `.env`를 사용하고,
`PROJECT`를 기존 컨테이너 label의 프로젝트명으로 지정한다. 새 clone 디렉터리명으로
프로젝트명을 추측하지 않는다. 아래 명령은 해당 운영 디렉터리에서 실행한다.

```bash
docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}'
docker inspect EXISTING_DB EXISTING_AGENT EXISTING_RABBITMQ \
  --format '{{.Name}} {{json .Mounts}}'
export PROJECT=liveguard-infra  # 실제 label과 일치할 때만 사용
```

확인된 실제 기본 프로젝트 볼륨은 `liveguard-infra_liveguard_db`,
`liveguard-infra_liveguard_agent_tasks`이다. Rabbit profile 활성 시
`liveguard-infra_liveguard_rabbitmq`로 매핑된다. 별도 기존 review 프로젝트들은 각자의
prefix를 사용한다. 테스트는 어느 기존 named volume도 마운트하지 않는다.
전체 `docker inspect` 또는 `compose config`를 공유하면 credential이 노출될 수 있으므로
선별 format 또는 `config --quiet`만 출력한다.

적용 전에 기존 MCP 및 Agent 컨테이너 image ID를 아래처럼 기록하고 rollback 태그로
보존한다. 기록 파일은 접근 제한된 운영 변경 기록에 둔다. 이전 Compose는 Infra
`abf54b11998ad1abbc05022ab190c348328eff8f`이다. 실제 이전 실행 이미지가 이 소스와
같다는 보장이 없으므로 추측한 이전 버전 대신 직접 확인한 ID를 보관한다.

별도 깨끗한 Agent checkout을 준비한다. 기존 팀원의 checkout을 reset하지 않는다.

```bash
git clone https://github.com/skalaP05-03-261019/liveguard-agent.git /new/path/liveguard-agent-ha
git -C /new/path/liveguard-agent-ha checkout --detach 764eab26a8272d72fc79bcad5b6e7aa82ef8d8b0
export AGENT_BUILD_CONTEXT=/new/path/liveguard-agent-ha
```

아래 전환 절차는 기존 Backend/DB가 실행 중인 환경을 전제로 한다.
실제 존재하는 조회용 case ID를 `MCP_VERIFY_CASE_ID` 환경변수에 설정한다.
값이나 응답 본문을 출력하지 않는다. `set -e`로 검증 실패 시 기존 MCP 교체 전에 중단한다.
두 신규 MCP를 모두 검증하는 것은 계획된 전환의 안전 조건이며,
LB 자체의 한 대 장애 허용 시작 조건과는 별개다.

```bash
set -eu
: "${MCP_VERIFY_CASE_ID:?Set an existing read-only verification case ID}"
docker inspect EXISTING_MCP EXISTING_AGENT --format '{{.Name}} {{.Image}}'
docker image tag ACTUAL_OLD_MCP_IMAGE_ID liveguard-business-mcp:pre-ha
docker image tag ACTUAL_OLD_AGENT_IMAGE_ID liveguard-agent:pre-ha
python3 scripts/verify-business-mcp-config.py --env-file .env \
  --project "$PROJECT" --output /tmp/business-mcp-predeploy.json
docker compose -p "$PROJECT" config --quiet
docker compose -p "$PROJECT" build business-mcp-1
# MCP 두 번째 build 없이 같은 이미지 재사용
docker compose -p "$PROJECT" up -d --no-deps --no-build --wait --wait-timeout 60 \
  business-mcp-1 business-mcp-2
# 기존 business-mcp를 교체하기 전에 각 신규 MCP를 통한 실제 인증 조회 검증.
for MCP_SERVICE in business-mcp-1 business-mcp-2; do
  docker compose -p "$PROJECT" exec -T -e MCP_VERIFY_CASE_ID "$MCP_SERVICE" python - <<'PYCODE'
import asyncio, os
from uuid import UUID, uuid4
from app.clients.business_mcp import BusinessMcpReadClient, BusinessMcpSettings
async def verify():
    client = BusinessMcpReadClient(BusinessMcpSettings(
        'http://127.0.0.1:8002/mcp', os.environ['BUSINESS_MCP_AGENT_TOKEN']))
    await client.call('get_moderation_case', {
        'caseId': str(UUID(os.environ['MCP_VERIFY_CASE_ID'])), 'traceId': str(uuid4())})
try:
    asyncio.run(verify())
except Exception:
    raise SystemExit('MCP authenticated read failed; cutover aborted') from None
print('PASS: authenticated read; body withheld')
PYCODE
done
docker compose -p "$PROJECT" run --rm --no-deps business-mcp \
  haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
docker compose -p "$PROJECT" up -d --no-deps --no-build business-mcp
# Agent 코드가 오래되었으면 먼저 새 소스로 agent만 build 후 재생성
docker compose -p "$PROJECT" build agent
docker compose -p "$PROJECT" up -d --no-deps --no-build agent
```

기존 `business-mcp` 컨테이너를 HAProxy로 교체할 때 연결이 끊길 수 있다.
무중단 전환을 보장하지 않는다. 변경 요청이 없는 유지보수 시간에 적용하고 진행 중
UNKNOWN action은 기존 actionId로 조회한다. 운영 볼륨 삭제/초기화/migration은 하지 않는다.
적용 후 같은 inspect 명령으로 mount source/name/destination을 전후 비교한다.

## 상태 확인, 장애, 복구

```bash
docker compose -p "$PROJECT" ps business-mcp business-mcp-1 business-mcp-2
docker compose -p "$PROJECT" images business-mcp-1 business-mcp-2
docker compose -p "$PROJECT" exec business-mcp wget -q -O /dev/null http://127.0.0.1:8002/ready
docker compose -p "$PROJECT" stop business-mcp-1
docker compose -p "$PROJECT" up -d --no-deps --no-build --force-recreate business-mcp-1
```

MCP와 LB는 호스트 포트를 추가하지 않는다. MCP Python urllib healthcheck는 `/ready`를
검사하고 LB BusyBox wget은 최소 하나의 정상 MCP로 실제 HTTP 전달이 되는지 검사한다.
두 MCP 모두 불가하면 LB 프로세스는 유지되며 503, container health는 unhealthy다.
`depends_on`은 초기 순서만 관리한다. 실행 중 제외/복귀는 HAProxy 1초, fall 2/rise 2
probe가 담당한다. Docker DNS 127.0.0.11:53 resolver로 IP 변경을 반영한다.
`hold valid 5s`를 서버 IP 갱신의 5초 SLA로 해석하지 않는다. 탐지 전/진행 중 요청 실패는 가능하며 실패를 성공으로 세지 않는다.

`/ready`는 프로세스 준비/drain만 나타내고 Backend 인증/통신 성공을 보장하지 않는다.
Backend 검증은 별도 인증된 MCP 도구 조회가 필요하다. 재현 시 응답 본문은 출력하지 않는다.
SIGTERM은 Agent의 기존 DrainingServer가 drain 표시 후 요청 완료를 기다린다.
실제 종료 시 listener도 빨리 닫혀 `/ready` 503을 외부에서 포착하지 못할 수 있다.
503 상태 전환은 application 테스트, 실제 진행 요청 완료는 Docker 테스트로 구분했다.
종료 유예 20초가 모든 요청의 성공을 보장하지 않는다. Agent 전체 deadline 10초가 먼저
만료될 수 있다. `unless-stopped`는 프로세스 종료 시 재시작하며 unhealthy만으로 재시작하지 않는다.

장애 분석은 container health/exit 상태, HAProxy 서버 UP/DOWN 이벤트, 안전한 오류 코드로
진행한다. HAProxy HTTP 요청 로그 및 Uvicorn access log는 비활성화한다. SDK/HTTP body
DEBUG 로깅을 켜지 않으며 토큰, 도구 인자, 원문 채팅, 응답 body를 수집하지 않는다.

## 롤백

1. 진행 중 변경을 확인하고 유지보수 시간을 확보한다. Agent URL은 변경하지 않는다.
2. 운영 checkout에서 변경 전 Compose (`abf54b11998ad1abbc05022ab190c348328eff8f`)를 복구한다.
   다른 미커밋 파일을 reset하지 않는다. 현재 Compose는 별도 보관한다.
3. 작은 rollback override로 `business-mcp.image: liveguard-business-mcp:pre-ha`,
   `agent.image: liveguard-agent:pre-ha`, `pull_policy: never`를 지정한다.
4. 같은 `-p "$PROJECT"`, 같은 `.env`로 `up -d --no-deps --no-build business-mcp agent`.
   이때 HAProxy가 이전 단일 MCP로 교체된다. 이전 고정 ID를 태그에서 확인한다.
5. 구성이 복구된 것을 확인한 뒤 남아 있는 `business-mcp-1/2` 컨테이너만 이름/label을
   확인하여 stop 및 rm한다. 전체 stack down이나 광범위 remove-orphans를 쓰지 않는다.
6. 기존 mount 및 실제 인증 조회를 다시 확인한다. 볼륨 삭제, SQLite 초기화는 금지한다.

## 재실행 가능한 격리 Docker 시험

```bash
export BUSINESS_MCP_IMAGE=liveguard-business-mcp:764eab26a827
export AGENT_BUILD_CONTEXT=/absolute/path/to/verified/liveguard-agent
python3 scripts/verify-business-mcp.py --env-file /absolute/path/to/existing/.env \
  --preserve-project liveguard-infra --preserve-project liveguard-final-review --preserve-project liveguard-main-review \
  --preserve-project liveguard-v1-review --output evidence/business-mcp-ha.json
```

Python 표준 라이브러리와 Docker Compose 2.24.4 이상(`!override` 지원)이 필요하다.
`--preserve-project`는 실제 존재하는 프로젝트만 반복 지정한다. 누락된 프로젝트는 실패하고,
옵션을 생략하면 mount 보존은 NOT RUN으로 기록한다. 비교는 mount 구성 확인이며 데이터 checksum 검사는 아니다.
Fixture는 실제 인증값을 안전한 env-file에서 읽되 출력하지 않고, 가상 조회 데이터와
source IP만 반환한다. 기존 Infra Compose에 임시 override를 적용한다. Backend만 fixture로
대체하고 무관한 RAG만 대기 프로세스로 격리한다. Agent→LB→MCP 및 MCP→Backend
의존성은 유지한 채 한 MCP를 unavailable로 만든 초기 시작을 검증한다. Agent API는
그대로 시작하되 gateway 미설정으로 업무 worker는 실행하지 않는다.
Agent 저장 경로는 컨테이너 `/tmp`이며 기존 SQLite나 checkpoint에 접근하지 않는다.
따라서 cold-start 및 degraded 재생성 결과는 Agent API 기동 및 Agent SDK 조회 성공이며 업무 runtime
전체 readiness나 실제 작업 처리 검증은 아니다. 기존 readiness 검증 조건은 완화하지 않는다.

임시 프로젝트만 `down --remove-orphans`로 정리하며 `down -v`, prune은 사용하지 않는다.
테스트 중 app 실패는 비정상 종료하며 증거에 failure를 기록한다. IP 보유 컨테이너로
재생성 후 IP가 실제 바뀌었는지 확인한다. probe 수렴 시간 뒤 각 조회는 한 번만 수행하며
실패 요청을 성공으로 간주하거나 자동 재시도하지 않는다.

## 관측 결과와 남은 인수

실제 Docker·정적 검증 결과는 `evidence/business-mcp-ha.json` 하나로 기록한다.
과거 Spring 조회 결과, 소스/명령/관측 한계는 `business-mcp-validation.md` 참조.
GitHub Actions는 `--portable` 정적 검증만 수행하며 로컬 빌드 소스 확인과 Docker 장애 시험을 대신하지 않는다.

실제 Spring Backend의 UNKNOWN 복구/중복 변경 효과는 **BE·Agent 공동 인수**다.
응답 유실 후 UNKNOWN → 원래 actionId 조회 → APPLIED 확인 시 재집행 금지,
미확인 시 신규 action 금지, execute POST 1회와 실제 변경 효과 1회를 함께 확인해야 한다.
Infra 가상 시험이나 기존 Agent 테스트만으로 완료 선언하지 않는다.
다중 Agent/Worker, 공유 Inbox migration, Checkpointer 변경, 전역 모델 동시성,
RAG 증설, exactly-once 신설은 범위 밖이다.
