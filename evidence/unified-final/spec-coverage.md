# PROJECT AC 검증 범위 (2026-10-21)

정책 기준: BE docs/policy/PROJECT.md·POLICY.md·TBD-decisions.md와 contracts/openapi.yaml. 시험 fixture와 정책 승인은 구분한다. report.json의 observed는 실제 OpenAI/Business/RAG MCP/Rabbit/BE/DB/독립 브라우저 시험이고, controlled는 Java PostgreSQL/Rabbit 및 Agent 체크포인트 테스트다.

| 항목 | 근거와 한계 |
|---|---|
| AC01 PASS | 실제 일반 채팅/SSE 관찰. PASS에서 Agent 조사 미발생은 Java 경로 검사 |
| AC02 욕설 | 필터·Backend 확정/첫 PROFANITY timeout0 통합 검사. 실제 UI 인용 사례는 이번 report 밖 |
| AC03 링크 | 공식 링크도 RULE 확정하는 #37 필터/Backend 통합 검사. 실제 UI 공식 링크는 이번 report 밖 |
| AC04 정상 | observed: HELD→AI 정상 제안→DEFER 유지→사람 정상→PUBLIC |
| AC05 위반 | observed: 사람 결정→HIDDEN/TIMEOUT403(until). AI 제안만으로 확정하지 않음 |
| AC06 숫자 | 필터 controlled. 숫자/패턴만으로 위반 확정 금지 |
| AC07 PII | Backend UNKNOWN 사실 차단/A16 NEEDS_REVIEW→CONTEXT·Agent interrupt controlled. 실제 검증 사실 공급 미완료 |
| AC08·09 FLOOD | PostgreSQL 4메시지 단일묶음/첫2 PUBLIC/3·4 HIDDEN 및 11초 뒤 재적발 controlled. UI 관찰은 report 확인 |
| AC10 제한 중 전송 | observed: TIMED_OUT403/until. 새 사건 가산 금지는 controlled |
| AC11 여러 유형 | 복수 규칙 태그/유형·한 사건·최장 timeout controlled |
| AC12·13 2건/3건 | observed: 별도3사건→KICK카드. checkpoint/재시작 보존은 Agent PostgreSQL controlled |
| AC14 강퇴 승인 | observed: 별도 사람 승인→동일thread 재개→MCP execute→대상 SSE 차단 |
| AC15 거절 | Backend·Agent controlled: 소진 유지, kick 미실행 |
| AC16·17 소진/취소/예약 | Backend controlled: 자기 소진만 유효, RELEASED 재예약, 복수 ban 중 취소한 소유권만 해제 |
| AC18 중복/worker 재시작 | Backend 멱등 집행·Agent 영속 재개·Rabbit 중복/lease/retry controlled. 실 브라우저 강제 worker kill 전체 시나리오는 미관찰 |
| AC19 24시간 초과 | 방송 종료 기준 KICK 접근 검사 구현. 실제24시간 경과 시험 미관찰 |
| AC20 새 방송 | PostgreSQL controlled: 이전 live 제재 미적용. FRESH_LIVE 브라우저 재실행에서도 이전 제한 계정 재전송 관찰 |
| AC21 timeout 만료 | 이력 보존·만료 접근 검사 controlled. 실제 벽시계 장시간 대기 시험 미관찰 |

추가 observed: 오판 finding취소→PUBLIC복구·전송허용, 동일쿠키 계정교체→운영자 카드/원문 초기화. 다른 hold 보존·다중 KICK 일부 취소·승인자 권한 회수 후 실행 거부는 Backend controlled 증거다.
