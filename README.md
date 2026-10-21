> 최신(2026-10-21): [7서비스·실제 AI·사람 승인·오판 복구 검증](docs/v1-integration.md)을 우선 참조하세요. 아래 5서비스/이전 미연동 설명은 당시 기록입니다. 현재 기본값은 미정 정책 fixture와 통합 화면을 자동 활성화하지 않습니다.

> 2026-10-21 후속: 실제 liveId 통합은 [시험 실행·검증 기록](docs/v1-integration.md)을 우선 참조하세요. 아래 앞선 5서비스 검증 기록은 당시 범위이며 전체 Agent 미연동이라는 문장은 후속 시험 설정에 적용되지 않습니다. 기본 구성은 여전히 Gateway·Outbox·새 화면·미정 정책 시험을 자동 활성화하지 않습니다.

# LIVE:GUARD Infra

LIVE:GUARD 프로젝트의 로컬 Docker 개발 환경을 관리하는 저장소입니다.

Docker Compose를 통해 PostgreSQL, Spring Boot Backend, FastAPI Agent, Business MCP, RAG MCP를 통합 실행합니다.

서비스별 소스 코드는 각 담당 저장소에서 관리하며, Infra 저장소에서는 컨테이너 실행, 환경변수, 서비스 간 통신 및 데이터 영속화를 관리합니다.

## 1. 시스템 구성

| 서비스       | 기술                     | 역할                                        | 로컬 포트 |
| ------------ | ------------------------ | ------------------------------------------- | --------- |
| db           | PostgreSQL 16 + pgvector | 서비스 데이터, 정책 벡터 및 체크포인트 저장 | 5433      |
| backend      | Spring Boot              | 서비스 API 및 운영 사건 데이터 처리         | 8080      |
| agent        | FastAPI + LangGraph      | AI 기반 운영 판단 및 작업 처리              | 8001      |
| business-mcp | MCP Server               | Backend 업무 조회 및 조치 Tool 제공         | 8002      |
| rag-mcp      | MCP Server               | 운영 정책 검색 및 원문 조회                 | 8003      |

모든 호스트 포트는 `127.0.0.1`에 바인딩합니다.

### 서비스 연결 구조

```text
                    Agent (8001)
                     /         \
                    v           v
           Business MCP       RAG MCP
              (8002)           (8003)
                 |                |
                 v                |
            Backend (8080)        |
                 |                |
                 +-------+--------+
                         |
                         v
                 PostgreSQL (5432)
```

Agent는 Business MCP 및 RAG MCP에 Docker 서비스 이름을 이용해 접근합니다.

Backend와 MCP 서버 간 내부 통신에는 서비스별 인증 토큰을 사용합니다.

## 2. 사전 준비

- Docker 및 Docker Compose
- `liveguard-infra`, `liveguard-be`, `liveguard-agent` 저장소
- RAG 정책 색인용 OpenAI API 키
- 로컬 실행에 필요한 인증 토큰 및 DB 접속 정보

저장소는 다음과 같이 동일한 상위 디렉터리에 배치합니다.

```text
projects/
├── liveguard-infra/
│   ├── compose.yaml
│   ├── compose.fresh-test.yaml
│   ├── .env.example
│   └── README.md
├── liveguard-be/
│   └── Dockerfile
├── liveguard-agent/
│   └── Dockerfile
└── liveguard-fe/
```

기본 Compose 구성에 Frontend가 포함되며 localhost:3000에서 접속합니다. 기존 5서비스 설정과 볼륨은 보존합니다.

Backend와 Agent 이미지는 각각 `../liveguard-be`, `../liveguard-agent`의 Dockerfile을 사용해 빌드합니다.

## 3. 로컬 환경 실행

### 3.1 환경변수 설정

`liveguard-infra` 디렉터리에서 실행합니다.

```bash
cp .env.example .env
```

`.env.example`을 참고해 `.env`에 실제 로컬 개발용 값을 입력합니다.

주요 환경변수는 다음과 같습니다.

| 변수                       | 용도                                          |
| -------------------------- | --------------------------------------------- |
| `POSTGRES_DB`              | PostgreSQL 데이터베이스 이름                  |
| `POSTGRES_USER`            | PostgreSQL 사용자                             |
| `POSTGRES_PASSWORD`        | PostgreSQL 비밀번호                           |
| `POSTGRES_PORT`            | 호스트 DB 포트                                |
| `INTERNAL_SERVICE_TOKEN`   | Business MCP에서 Backend 내부 API 접근        |
| `BUSINESS_MCP_AGENT_TOKEN` | Agent에서 Business MCP 접근                   |
| `RAG_MCP_AGENT_TOKEN`      | Agent에서 RAG MCP 접근                        |
| `AGENT_SERVICE_TOKEN`      | Agent 작업 API 접근 인증                      |
| `RAG_DB_URL`               | RAG 정책 저장용 PostgreSQL 연결 주소          |
| `LIVEGUARD_OPENAI_API_KEY` | 모델 호출 및 정책 임베딩                           |
| `AGENT_CHECKPOINT_DB_URL`  | LangGraph Checkpointer용 PostgreSQL 연결 주소 |

인증 토큰은 서로 구분해 설정하며, 다음 명령어로 생성할 수 있습니다.

```bash
openssl rand -hex 32
```

`RAG_DB_URL`과 `AGENT_CHECKPOINT_DB_URL`은 컨테이너 내부 주소인 `db:5432`를 사용합니다. DB 비밀번호에 특수문자가 포함되면 URL 인코딩이 필요합니다.

`AGENT_TASK_DB_PATH`는 Compose에서 `/var/lib/liveguard-agent/tasks.sqlite3`로 지정하며, Docker 볼륨을 통해 영속화합니다.

**주의 사항**

- `.env`에는 실제 인증 정보가 포함되므로 Git에 커밋하지 않습니다.
- `.env.example`에는 실제 비밀번호와 API 키를 입력하지 않습니다.
- 셸 환경변수가 `.env`보다 우선 적용될 수 있으므로 값이 반영되지 않으면 셸 환경변수도 확인합니다.

### 3.2 Compose 설정 검증

```bash
docker compose config --quiet
```

오류 없이 종료되면 Compose 설정이 유효합니다.

### 3.3 서비스 빌드 및 실행

```bash
docker compose up -d --build
```

실행 상태를 확인합니다.

```bash
docker compose ps
```

로그 확인:

```bash
docker compose logs backend --tail=100
docker compose logs agent --tail=100
docker compose logs business-mcp --tail=100
docker compose logs rag-mcp --tail=100
```

### 3.4 Healthcheck

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

`readyForTasks`는 서비스별 실제 준비 조건에 따라 달라집니다.

현재 Agent는 실제 Backend ModerationGateway 연결이 완료되지 않아 `readyForTasks: false`를 반환할 수 있습니다. 이는 컨테이너 실행 실패와 구분해야 합니다.

## 4. PostgreSQL 및 데이터베이스 관리

PostgreSQL은 `pgvector/pgvector:pg16` 이미지를 사용합니다.

Backend의 업무 스키마와 마이그레이션은 Flyway로 관리하고, RAG 및 Agent 체크포인트 데이터는 각각 별도의 스키마를 사용합니다.

| 스키마     | 관리 대상                    |
| ---------- | ---------------------------- |
| `platform` | 사용자, 채널, 채팅 메시지    |
| `guard`    | 운영 사건, 후보, 판단 데이터 |
| `rag`      | 정책 Chunk 및 Embedding      |
| `agent`    | LangGraph Checkpoint         |

### 4.1 Flyway 마이그레이션

주요 마이그레이션:

| 파일                                 | 역할                                |
| ------------------------------------ | ----------------------------------- |
| `V100__schemas_and_extensions.sql`   | 스키마 및 pgvector 설정             |
| `V101__platform_core.sql`            | Platform 핵심 테이블 생성           |
| `V200__guard_cases_and_findings.sql` | Guard 사건 및 판단 관련 테이블 생성 |
| `R__dev_seed.sql`                    | 개발용 초기 데이터                  |

마이그레이션 파일은 `liveguard-be` 저장소에서 관리합니다.

Flyway 이력 확인:

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "SELECT installed_rank, version, description, success FROM flyway_schema_history ORDER BY installed_rank;"
```

Guard 테이블 확인:

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "\dt guard.*"
```

### 4.2 pgvector 확인

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

로컬 통합 검증에서 pgvector 0.8.7을 확인했습니다.

## 5. RAG MCP 정책 색인

RAG MCP는 운영 정책을 Chunk 단위로 분리하고 OpenAI Embedding API를 통해 벡터화한 뒤 PostgreSQL의 `rag.policy_chunks`에 저장합니다.

최초 실행 시 정책 색인이 필요합니다.

```bash
docker compose run --rm --no-deps rag-mcp \
  python -m app.rag_mcp.index
```

해당 명령어는 OpenAI API를 호출하므로 사용량에 따른 비용이 발생할 수 있습니다.

동일 정책 버전을 다시 색인하면 기존 버전 데이터를 교체하므로, 불필요한 반복 실행은 피합니다.

### 5.1 색인 결과 확인

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "SELECT version, count(*) AS sections FROM rag.policy_chunks GROUP BY version ORDER BY version;"
```

2026-10-21 로컬 검증 결과:

- 정책 버전: 3.1
- 색인 조항: 29개
- Embedding 모델: `text-embedding-3-small`

### 5.2 MCP Tool 검증

Agent 컨테이너에서 RAG MCP 클라이언트를 이용해 다음 Tool 호출을 검증했습니다.

- `search_policy`: 정책 검색 성공
- `get_policy_section`: 정책 ID 기반 원문 조회 성공

정책 검색 결과의 정확도와 전체 AI 판단 품질은 별도 검증 대상입니다.

## 6. Business MCP 연동

Business MCP는 Agent에서 Backend 업무 기능에 접근하기 위한 MCP 서버입니다.

Docker 내부 접속 주소:

```text
http://business-mcp:8002/mcp
```

MCP SDK의 Host 검증에 대응하기 위해 다음 호스트를 허용합니다.

```text
business-mcp:*,localhost:*,127.0.0.1:*
```

2026-10-21 로컬 통합 검증에서 HTTP 421 Host 오류를 해결하고, Agent에서 Business MCP 인증 및 MCP Tool 목록 조회에 성공했습니다.

확인된 Tool은 읽기 7개 및 조치 관련 5개를 포함한 총 12개입니다.

단, Tool 목록 조회 성공이 모든 업무 API의 실제 실행 성공을 의미하지는 않습니다.

실제 운영 사건 조회 및 조치 실행은 Backend 데이터와 구현 상태에 따라 추가 검증이 필요합니다.

## 7. Agent 작업 저장소

Agent는 작업 접수 및 실행 상태 관리를 위해 SQLite 기반 TaskStore를 사용합니다.

```text
/var/lib/liveguard-agent/tasks.sqlite3
```

SQLite WAL 및 잠금 파일도 같은 디렉터리에 생성될 수 있으므로, 파일이 아닌 디렉터리 전체를 Docker 볼륨으로 영속화합니다.

```text
liveguard_agent_tasks
    → /var/lib/liveguard-agent
```

Agent 컨테이너는 UID 10001로 실행되므로 저장 디렉터리에 쓰기 권한이 필요합니다.

### 7.1 최초 볼륨 권한 설정

볼륨을 생성합니다.

```bash
docker compose create --no-recreate agent
```

기본 Compose 프로젝트 이름을 사용하는 경우 다음과 같은 볼륨이 생성됩니다.

```text
liveguard-infra_liveguard_agent_tasks
```

실제 이름은 다음 명령어로 확인합니다.

```bash
docker volume ls
```

해당 Agent 전용 볼륨의 소유권을 설정합니다.

```bash
docker run --rm \
  --user 0:0 \
  -v liveguard-infra_liveguard_agent_tasks:/data \
  alpine:3.20 \
  sh -c 'chown 10001:10001 /data && chmod 700 /data'
```

볼륨 이름은 실제 환경에 맞게 변경합니다.

설정 후 Agent 컨테이너를 재생성합니다.

```bash
docker compose up -d --no-deps --force-recreate agent
```

### 7.2 영속성 검증

로컬 테스트에서 별도의 SQLite 검증 파일을 생성한 뒤 Agent 컨테이너를 재생성해도 데이터가 유지되는 것을 확인했습니다.

이 검증은 Docker 볼륨의 데이터 보존을 확인한 것으로, 실제 Agent TaskStore의 업무 복구 전체를 검증한 것은 아닙니다.

## 8. LangGraph Checkpointer

Agent는 LangGraph 실행 상태를 PostgreSQL의 `agent` 스키마에 저장합니다.

Checkpointer 연결 주소는 `AGENT_CHECKPOINT_DB_URL` 환경변수로 전달합니다.

### 8.1 최초 Checkpointer 초기화

다음 명령어는 PostgreSQL에 `agent` 스키마 및 체크포인트 테이블을 생성합니다.

**DB 구조를 변경하는 초기화 작업이므로 최초 실행 시에만 필요한지 확인하고 수행합니다.**

```bash
docker compose run --rm --no-deps agent python -c '
import asyncio
import os
from app.harness.checkpoint import open_checkpointer

async def main():
    async with open_checkpointer(
        os.environ["AGENT_CHECKPOINT_DB_URL"]
    ):
        print("LangGraph Checkpointer initialization: SUCCESS")

asyncio.run(main())
'
```

생성된 테이블 확인:

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'agent' ORDER BY table_name;"
```

2026-10-21 로컬 검증에서 다음 4개 테이블의 생성을 확인했습니다.

- `agent.checkpoints`
- `agent.checkpoint_blobs`
- `agent.checkpoint_writes`
- `agent.checkpoint_migrations`

테스트용 Checkpoint를 저장하고 동일 프로세스에서 복원하는 검증도 성공했습니다.

다만 실제 LangGraph 업무 중단 및 재개, 컨테이너 재생성 후 작업 복구까지 검증한 것은 아닙니다.

## 9. 독립 테스트 환경

`compose.fresh-test.yaml`은 Backend 및 PostgreSQL을 기본 개발 환경과 분리된 포트 및 데이터 볼륨으로 검증하기 위한 구성입니다.

```bash
docker compose -p liveguard-clean-test \
  -f compose.fresh-test.yaml up -d --build
```

상태 확인:

```bash
docker compose -p liveguard-clean-test \
  -f compose.fresh-test.yaml ps
```

테스트 포트:

- PostgreSQL: 15433
- Backend: 18080

별도 Compose 프로젝트 이름을 사용하여 기본 개발 환경과 볼륨을 구분합니다.

테스트 종료:

```bash
docker compose -p liveguard-clean-test \
  -f compose.fresh-test.yaml down
```

## 10. 서비스 종료 및 재시작

일시 중지:

```bash
docker compose stop
```

재시작:

```bash
docker compose start
```

컨테이너 종료 및 제거:

```bash
docker compose down
```

일반적인 `docker compose down`은 named volume을 삭제하지 않습니다.

**주의:** `docker compose down -v`는 PostgreSQL 및 Agent 작업 볼륨을 삭제할 수 있으므로 데이터 보존이 필요한 경우 사용하지 않습니다.

## 11. 저장소별 관리 범위

| 저장소            | 담당 영역                                        |
| ----------------- | ------------------------------------------------ |
| `liveguard-infra` | Docker Compose, 컨테이너, 서비스 연결, 영속 볼륨 |
| `liveguard-be`    | Spring Boot, Backend API, Flyway                 |
| `liveguard-agent` | AI Agent, Business MCP, RAG MCP, LangGraph       |
| `liveguard-fe`    | Frontend                                         |

각 저장소의 코드와 업무 로직은 해당 담당 저장소에서 관리하고, 로컬 통합 실행 환경은 Infra 저장소에서 관리합니다.

## 12. 현재 검증 상태 및 남은 작업

### 검증 완료

- [x] PostgreSQL 및 pgvector 실행
- [x] Backend Docker 빌드 및 Flyway V200 적용
- [x] Business MCP Docker 통합 및 Host 검증 문제 해결
- [x] Business MCP 인증과 Tool 목록 조회
- [x] RAG MCP 정책 v3.1 색인
- [x] RAG MCP 정책 검색 및 원문 조회
- [x] Agent Docker 빌드 및 HTTP 서버 실행
- [x] Agent SQLite 영속 볼륨 및 재생성 후 데이터 유지
- [x] PostgreSQL LangGraph Checkpointer 초기화
- [x] Checkpointer 테스트 데이터 저장 및 조회

### 추가 작업

- [ ] 실제 Backend ModerationGateway 연동
- [ ] Agent Runtime 준비 상태 검증
- [ ] Backend 실제 사건 데이터 기반 Business MCP 조회 검증
- [ ] Agent 전체 업무 실행 및 복구 E2E 검증
- [ ] Frontend Docker 통합
- [ ] 전체 서비스 통합 테스트

현재 Agent는 실제 Backend ModerationGateway가 연결되지 않아 `readyForTasks: false`를 반환합니다.

Infra 설정만으로 이를 임의로 활성화하지 않으며, Backend 및 Agent 구현이 준비된 이후 실제 통합 테스트를 진행합니다.
