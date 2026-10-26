# 원격 main 배포·헬스체크 및 청중 시드

## 범위와 전제

`scripts/deploy-main.py`는 Infra의 현재 Compose와 **각 실행 시점에 fetch한 BE·Agent·FE
origin/main 커밋**을 배포한다. 형제 저장소는 origin 주소를 읽는 용도로만 사용한다.
기존 작업 브랜치를 checkout/reset/stash하지 않는다. 배포 checkout은 기본적으로
`.deploy/<project>/sources/`에 생성하고, 이후 fetch + main의 fast-forward만 허용한다.
dirty checkout, 다른 origin, ahead/diverged main은 실패한다. 배포 중 main이 갱신되어도
한 번 선택한 커밋을 유지하며 다음 실행에서 새 main을 가져온다.

필수 도구는 Python 3.10 이상, Git, Docker Compose(`--wait` 지원)다.
형제 `liveguard-be`, `liveguard-agent`, `liveguard-fe` 저장소와 각 origin 접근 권한이 필요하다.
`.env`는 먼저 준비하며 기존 인증정보를 다시 발급하거나 덮어쓰지 않는다.

```dotenv
AGENT_GATEWAY_FACTORY=app.integration.http_gateway:configured_gateway
MODEL_PROVIDER=openai
MODEL_NAME=<실제 사용할 모델>
MODEL_MAX_INPUT_TOKENS=20000
LIVEGUARD_OPENAI_API_KEY=<로컬에서만 입력>
LIVEGUARD_POLICY_VERSION=v3.2
AGENT_DELIVERY_ENABLED=true
RAG_DB_URL=<db:5432를 사용하는 정책 DB DSN>
AGENT_CHECKPOINT_DB_URL=<db:5432를 사용하는 checkpoint DB DSN>
```

나머지 DB·서비스 token도 `.env.example`에 따라 설정한다. 이 값들은 예시이며
실제 API 키를 자동 생성하지 않는다. `MODEL_NAME`에는 팀이 선택하고 해당 키로 접근 가능한
Chat Completions/function calling 모델 ID를 지정한다(예: `gpt-4.1-mini`; 자동 선택하지 않음).
임베딩 모델 `text-embedding-3-small`과 조사 모델 `MODEL_NAME`은 서로 다르다.

`OPENAI_API_KEY`에 이미 키를 넣었다면 중복 입력할 필요가 없다.
Compose는 비어 있지 않은 `LIVEGUARD_OPENAI_API_KEY`를 우선 사용하고, 없으면
`OPENAI_API_KEY`를 Agent의 `MODEL_API_KEY`와 RAG의 `OPENAI_API_KEY`로 전달한다.
호스트 `.env`의 `MODEL_API_KEY` 자체는 Compose 입력으로 사용하지 않는다.
`AGENT_GATEWAY_FACTORY=app.integration.http_gateway:configured_gateway`는 기존 Agent가
실제 Backend 어댑터를 만들게 하는 설정이다. 별도 Gateway 서버/가입/API 키가 필요한 것이
아니며 Compose의 `BACKEND_BASE_URL`과 서비스 token을 사용한다.

배포는 컨테이너 시작 뒤 readiness 검사 전에 `python -m app.rag_mcp.index`를
v3.2로 **한 번** 실행한다. v3.1 색인이 이미 있으면 그대로 보존하고,
없는 새 DB에서는 v3.1로 한 번 추가 실행한다. 각 실행에 `LIVEGUARD_POLICY_VERSION`과
`POLICY_VERSION`을 동일하게 지정하며 실행 중인 Backend/RAG의 활성 버전은 바꾸지 않는다.
Agent의 색인 구현은 선택한 버전만 트랜잭션 교체하므로 다른 버전을 삭제하지 않는다.
외부 OpenAI embedding 호출과 비용이 발생하며, 실패 시 자동 재시도 없이 배포가 실패한다.
`--sync-only`/`--check-only`는 색인을 실행하지 않는다.
키·모델·Gateway·RAG DB 설정 누락은 컨테이너 변경 전에 실패한다.
컨테이너가 뜬 뒤 색인/연결/readiness가 부족해도 성공 처리하지 않는다.

Compose는 단일 Agent 런타임·기존 SQLite 볼륨 구성이다. 공유 Inbox·다중 Worker 배포가 아니다.
모델의 20,000 입력 토큰 상한은 모델 처리 설정이며 출력 토큰·전역 quota 설정을 대신하지 않는다.

## 실행

항상 Infra에서 실행한다. `--env-file` 기본값은 Infra의 `.env`다.

```bash
# 소스만 동기화: 빌드/컨테이너/DB 변경 없음
python3 scripts/deploy-main.py --sync-only

# 기본 프로젝트명은 liveguard-infra. 기존 프로젝트가 다르면 실제 label과 일치시킨다.
python3 scripts/deploy-main.py --env-file .env --project liveguard-infra --rabbit

# 마지막 배포 조합을 재검사: fetch/build/up/시드 없음
python3 scripts/deploy-main.py --env-file .env --project liveguard-infra --check-only
```

`--source-dir`로 별도 소스 저장 위치를 지정할 수 있다. 해당 디렉터리는 배포 전용으로 사용하고
서로 다른 project가 같은 source-dir을 동시에 사용하지 않는다.
`--rabbit`은 최초 배포에서만 선택하며 check-only는 기록된 profile을 사용한다.
`--timeout` 기본 180초는 Compose 시작 대기와 후속 readiness 대기에 각각 적용된다.

BE·FE·Agent는 각각 전체 소스 SHA를 포함한 태그로 빌드한다. Business MCP 2대와 RAG는
같은 Agent 이미지를 재사용한다. 기존 `.env`의 과거 `*_BUILD_CONTEXT`와
`BUSINESS_MCP_IMAGE`는 이 워크플로의 runtime override로 대체한다.
버전별 checkout을 clean 상태로 유지하며 `Dockerfile`과 의존성은 각 main 것을 그대로 사용한다.
태그는 소스 추적용이며 재빌드의 bit-for-bit 재현성이나 공급망 인증을 보장하지 않는다.
DB·RabbitMQ·HAProxy 이미지는 로컬에 없을 때만 pull하며 기존 이미지/데이터를 임의 갱신하지 않는다.

이후 수동 `up`/`run`에도 위와 같이 runtime override를 함께 지정해야 한다.
`docker compose up`만 실행하면 `.env`의 과거 source 경로/이미지로 돌아갈 수 있다.
배포 갱신은 되도록 이 스크립트로만 수행한다.

환경변수 우선순위는 Docker Compose와 같다(셸 > 지정 env 파일). 설정 전체를 출력하면
비밀이 노출되므로 스크립트는 렌더링 결과·빌드 출력을 출력하지 않는다.
실패 시 서비스명/종류를 확인하고 필요한 서비스의 로그만 로컬에서 확인한다.
출력·공유 전에 token·본문을 제거한다.

## 헬스체크와 결과

- 선택된 모든 컨테이너 running, 정의된 Docker healthcheck healthy.
- 실행 중 이미지 ID가 선택된 이미지 ID와 동일, Agent 입력 토큰 설정 반영.
- FE HTTP 200, FE 프록시/BE 세션 API의 비인증 401.
- HAProxy 및 MCP 2대 `/ready` 200.
- Agent·RAG `readyForTasks: true`, RAG `/health`에 **v3.1·v3.2 모두** 및 활성 정책 버전 존재.
- 공통 Business MCP·RAG 인증된 MCP handshake/tools 목록.
- 공통 LB와 각 MCP에서 실제 BE로 인증된 읽기 호출. 임의의 없는 case가
  `NOT_FOUND`를 반환해야 통과한다(실제 데이터 생성·모델·변경 도구 호출 없음).

`.deploy/<project>/runtime.json`은 비밀 없는 이미지/소스 override다.
`deployment.json`에는 소스 SHA, 실제 이미지 ID, Infra HEAD/dirty 여부, env 경로, profile, 배포 상태를 기록한다.
실제 env 값은 저장하지 않는다. `READY`는 위 readiness를 통과했다는 뜻이며
전체 AI 조사·승인·장애 복구·브라우저 시나리오 성공을 뜻하지 않는다.
check-only는 기존 배포 기록을 바꾸지 않으며 현재 결과를 종료 코드로 알린다.

실패는 exit 1이며 설정 누락·헬스 실패를 성공으로 숨기지 않는다.
자동 rollback, `down`, 볼륨 삭제, DB 초기화는 하지 않는다. `up` 후 실패한 컨테이너는
원인 진단을 위해 남는다. DB migration은 BE가 시작하며 자동 수행하므로 중요한 DB는
별도 백업한다. 이미지 rollback이 migration rollback을 의미하지 않는다.
이전 버전으로 되돌릴 때는 이전 기록의 소스/이미지를 기준으로 수동 배포한다.
과거 고정 커밋만 받는 `verify-business-mcp-config.py`는 과거 HA 인수 검사용으로
유지하며, 이동하는 main 배포의 provenance 검증에는 이 새 워크플로를 사용한다.

## 청중 p001~p200 — 로컬 시연 DB 전용 (#8)

```bash
# readiness 성공 후에만 시드 적용. 운영/공용 DB에는 절대 사용하지 않는다.
python3 scripts/deploy-main.py --env-file .env --rabbit --seed-demo-participants

# 이미 준비한 로컬 DB에 SQL만 적용
docker compose exec -T db sh -c \
  'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < scripts/seed-demo-participants.sql
```

- username `p001`~`p200`, nickname `참여자 001`~`참여자 200`.
- ID `10000000-0000-4000-8001-000000000001`~`10000000-0000-4000-8001-000000000200`.
- 계정/채널 A 멤버십 모두 VIEWER. 정확한 ID 200개만 등록하며 임의의 `p999` 등을 포함하지 않는다.
- `viewer`의 현재 해시 복사. 기본 비밀번호는 **liveguard-local**이다.
  이슈 표의 `liveguard`와 달리 제안 SQL의 해시 복사 방식을 채택했다.
- viewer/채널이 없으면 실패한다. 기존 ID/username/역할/해시/닉네임/멤버십 충돌도 실패하며
  덮어쓰지 않는다. 한 트랜잭션에서 정확히 200개 상태를 검증하고 반복 실행해도 같다.
- 최종 시연 DB에는 200개가 남는다. 실제 청중에게 배포하기 전 로그인·방송 접근을 리허설한다.
  채팅/사건이 생긴 계정은 참조 때문에 임의 삭제하지 않는다.

휴대폰 접속이 필요한 행사장 로컬 환경에서만 `.env`에 `FRONTEND_BIND=0.0.0.0`을 설정한다.
기본은 `127.0.0.1`이며 DB·BE·Agent는 외부로 열지 않는다. 방화벽/네트워크 격리를 확인하고
시연이 끝나면 loopback으로 되돌린다. FE main의 `docs/participatory-demo.md`도 참고한다.

## 검증

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
# 반드시 로컬 시연 DB에서만. 테스트 변경은 전부 트랜잭션 종료/연결 종료 시 rollback.
LIVEGUARD_TEST_LOCAL_SEED=1 python3 -m unittest discover -s scripts -p 'test_seed_participants.py' -v
```
