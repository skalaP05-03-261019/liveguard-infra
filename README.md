# LIVE:GUARD Infra

> **2026-10-21 전체 서비스 로컬 연결:** [실행 방법·검증 결과·미연결 구간](docs/full-stack.md).
> `compose.full.yaml`을 추가하면 Frontend·Agent·Business MCP·RAG MCP까지 실행합니다.
> 기존 아래의 DB/Backend 실행 방법은 그대로 사용할 수 있습니다. AI 판정·승인 E2E는 Backend 미구현 API로 아직 완료되지 않았습니다.

LIVE:GUARD 프로젝트의 로컬 Docker 개발 환경을 관리하는 저장소입니다.

현재 PostgreSQL과 Spring Boot Backend를 Docker Compose로 통합 실행할 수 있습니다. 데이터베이스 스키마와 초기 데이터는 Backend의 Flyway 마이그레이션을 통해 관리합니다.

## 1. 현재 구성

| 항목         | 기술           | 설명                       |
| ------------ | -------------- | -------------------------- |
| Container    | Docker Compose | 로컬 서비스 통합 실행      |
| Database     | PostgreSQL 16  | 서비스 데이터 저장         |
| Extension    | pgvector       | 벡터 데이터 지원           |
| Backend      | Spring Boot    | API 서버                   |
| DB Migration | Flyway         | 스키마 및 개발용 시드 관리 |

Frontend, AI Agent, MCP 서버는 추후 통합할 예정입니다.

## 2. 사전 준비

- Docker 및 Docker Compose
- `liveguard-infra`, `liveguard-be` 저장소

두 저장소는 동일한 상위 디렉터리에 배치해야 합니다.

```text
projects/
├── liveguard-infra/
│   ├── .env.example
│   ├── .gitignore
│   ├── compose.yaml
│   ├── compose.fresh-test.yaml
│   └── README.md
└── liveguard-be/
    ├── Dockerfile
    └── ...
```

Backend 이미지 빌드에는 `../liveguard-be/Dockerfile`을 사용합니다.

## 3. 로컬 환경 실행

### 3.1 환경변수 설정

`liveguard-infra` 디렉터리에서 실행합니다.

```bash
cp .env.example .env
```

`.env` 파일에 로컬 개발 환경에 사용할 PostgreSQL 접속 정보를 설정합니다.

```dotenv
POSTGRES_DB=liveguard
POSTGRES_USER=liveguard
POSTGRES_PASSWORD=change-me
POSTGRES_PORT=5433
```

`POSTGRES_PASSWORD`는 개인 개발용 비밀번호로 변경합니다. `.env` 파일은 Git에 커밋하지 않습니다.

### 3.2 Docker Compose 설정 확인

```bash
docker compose config --quiet
```

오류 없이 종료되면 Compose 설정이 유효합니다.

### 3.3 서비스 빌드 및 실행

```bash
docker compose up -d --build
```

PostgreSQL과 Backend 컨테이너가 실행됩니다. Backend는 PostgreSQL의 Healthcheck가 통과한 후 시작됩니다.

### 3.4 실행 상태 확인

```bash
docker compose ps
```

기대 상태:

- `db`: Up (healthy)
- `backend`: Up

Backend가 실행되지 않으면 로그를 확인합니다.

```bash
docker compose logs backend --tail=100
```

## 4. 서비스 접속 정보

| 서비스     | 호스트    | 포트 |
| ---------- | --------- | ---- |
| PostgreSQL | localhost | 5433 |
| Backend    | localhost | 8080 |

Docker Compose 내부에서는 Backend가 `db:5432`를 통해 PostgreSQL에 연결합니다.

데이터베이스명, 사용자명, 비밀번호는 `.env`에 설정된 값을 사용합니다.

## 5. 데이터베이스 초기화

새 데이터베이스에서는 Backend의 Flyway 마이그레이션을 통해 스키마와 개발용 시드 데이터가 적용됩니다.

현재 확인된 주요 마이그레이션:

| 파일                               | 역할                         |
| ---------------------------------- | ---------------------------- |
| `V100__schemas_and_extensions.sql` | Schema 및 pgvector 생성      |
| `V101__platform_core.sql`          | Platform 핵심 테이블 생성    |
| `R__dev_seed.sql`                  | 로컬 개발용 초기 데이터 생성 |

마이그레이션 SQL은 `liveguard-be` 저장소에서 관리합니다.

### 5.1 Flyway 이력 확인

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "SELECT installed_rank, version, description, success FROM flyway_schema_history ORDER BY installed_rank;"
```

### 5.2 테이블 확인

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "\dt platform.*"
```

### 5.3 pgvector 확인

```bash
docker compose exec db \
  psql -U liveguard -d liveguard \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

최초 통합 검증에서는 pgvector 0.8.7을 확인했습니다.

## 6. 독립 테스트 환경

`compose.fresh-test.yaml`은 기본 개발 환경과 다른 포트 및 데이터 볼륨을 이용해 Backend와 PostgreSQL을 검증하기 위한 파일입니다.

```bash
docker compose -p liveguard-clean-test \
  -f compose.fresh-test.yaml up -d --build
```

실행 상태 확인:

```bash
docker compose -p liveguard-clean-test \
  -f compose.fresh-test.yaml ps
```

테스트 환경 접속 포트:

- PostgreSQL: 15433
- Backend: 18080

프로젝트 이름에 따라 별도의 Docker 볼륨이 생성됩니다. 단, 동일한 프로젝트 이름으로 재실행하면 기존 볼륨을 재사용할 수 있습니다.

테스트 종료:

```bash
docker compose -p liveguard-clean-test \
  -f compose.fresh-test.yaml down
```

## 7. 종료 및 재시작

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

**주의:** `docker compose down -v`는 해당 Compose 프로젝트의 DB 볼륨을 삭제할 수 있으므로 데이터 보존이 필요한 경우 사용하지 않습니다.

## 8. 저장소별 관리 범위

| 저장소            | 관리 영역                              |
| ----------------- | -------------------------------------- |
| `liveguard-infra` | Docker Compose, 서비스 연결, 실행 환경 |
| `liveguard-be`    | Backend 코드, Dockerfile, Flyway       |
| `liveguard-agent` | AI Agent 코드 및 실행 설정             |
| `liveguard-fe`    | Frontend 코드 및 실행 설정             |

각 서비스의 소스 코드는 해당 저장소에서 관리하고, 통합 실행 환경은 Infra 저장소에서 관리합니다.

## 9. 향후 작업

- [x] PostgreSQL 및 pgvector 로컬 실행
- [x] Backend Docker Compose 통합
- [x] 신규 DB에서 Flyway 마이그레이션 검증
- [x] Backend API 통합 동작 검증
- [ ] AI Agent Docker 통합
- [ ] MCP 서버 Docker 통합
- [ ] Frontend Docker 통합
- [ ] 전체 서비스 통합 테스트
