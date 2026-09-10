# Architecture

앱은 도메인 상태(`TripState`)를 중심으로 동작합니다. 모든 사용자 변화는 버전과 요청 ID가 있는 이벤트로 저장되며, 저장소의 compare-and-set으로 오래된 업데이트를 거부합니다.

```text
React UI
  └─ FastAPI routes ── Intake / Event / Decision services
                         ├─ SQLite repository (state, events, runs, proposals)
                         ├─ Monitor (scheduled weather checks)
                         └─ Replanner graph ── ToolProvider (Google/Open-Meteo)
```

공급자 원문은 일정 상태와 분리해 관측값으로 정규화합니다. 누락된 영업시간·경로·날씨는 `unknown`으로 남기며, 검증을 통과한 대안만 사용자에게 표시합니다. API 키는 서버 환경변수로만 읽습니다.
