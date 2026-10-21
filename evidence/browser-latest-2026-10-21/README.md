# 최신 BE 반영 후 역할별 브라우저 재검증

- 일시: 2026-10-21 KST
- Backend main: `71130fa5ea7e5b6c14a2f985f8fb9653570eaeb9` (#24 조회 구현, #22 기존 후보 참조 유지보수 병합 포함)
- 환경: 기존 로컬 `liveguard-connected` Spring/Postgres/FE. HTTP 응답 mock 없음.
- 실제 Chrome 창: 127.0.0.1:3000 스트리머(moderator), viewer.localhost:3000 시청자(viewer), localhost:3000 관리자(admin) 로그인 복구. 기존 창 배치와 DB 보존. 비밀번호 저장하지 않음.
- 자동 브라우저 검사: `result.json`의 9개 검사 통과. 별도 작성자가 아닌 시청자 세션에서도 정상 채팅 수신과 HELD 원문 비전달을 검증함.
- 네이티브 스트리머 화면에서도 이번 실행의 `b535a20fb552` 정상/격리/후속 정상 채팅 도착을 확인함.

`viewer.png`, `operator.png`, `observer.png`, `admin.png`는 자동 검사 브라우저 캡처이며 사용자 Chrome 창 캡처와 구분한다. 검증용 채팅은 로컬 DB에 남긴다. 실제 모델 호출과 제재 실행은 없음.

## 남은 연결

- `/api/cases` 404: 사건 목록·검토 결정·Agent 재개까지 전체 연결 검증 불가. 빈 추방 대상 목록을 판정 정상의 증거로 삼지 않는다.
- 관리자 SystemPage 통계는 `systemMock`. 화면 숫자는 실제 AI 처리량이 아니다.
- 임시 비노출은 현재 BE 필터 처리이며 실제 AI 추론 성공을 의미하지 않는다.
- Agent Gateway 미설정 상태 유지. 승인 우회나 fixture 메타데이터의 실제 DB 주입 없음.
