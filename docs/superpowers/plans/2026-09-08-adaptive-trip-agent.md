# Adaptive Trip Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. This session defaults to inline execution with executing-plans; do not dispatch agents unless the user chooses delegation.

**Goal:** 국내외 여행 일정의 상태를 유지하고 변화 발생 시 기본 3개 대안을 검증·제안하며 사용자 선택을 반영하는 포트폴리오 앱을 완성한다.

**Architecture:** Python 모듈형 백엔드가 여행 상태와 검증·확정을 관리하고 LangGraph가 제한된 도구 호출과 후보 수정을 연결한다. React 화면은 서버의 확정 상태와 제안을 표시한다. SQLite를 확정 상태의 단일 저장소로 사용하며 사용자 선택 대기는 그래프 실행을 종료한 뒤 DB의 pending 제안으로 유지한다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, LangGraph, httpx, SQLite(sqlite3), pytest, React·TypeScript·Vite, Vitest·Testing Library·Playwright. LLM은 주입 가능한 ModelGateway로 분리하고 모델 ID는 환경 설정으로 받는다.

**Spec:** ../specs/2026-09-08-adaptive-trip-agent-design.md

## Global Constraints

- 대상은 국내외 여행자 전체다. 특정 국가나 도시로 입력을 제한하지 않는다.
- 기본 3개의 구별되는 대안을 제안하고 변경 이유와 영향을 설명한다.
- 통과한 후보가 3개 미만이면 가능한 수만 제시하고 이유를 설명한다.
- 재계획이 진행되는 동안 확정 일정을 수정하지 않는다.
- 사용자 동의 없이 고정 조건을 변경하지 않는다.
- 미확인 정보를 통과로 세지 않는다. 위치·지출은 사용자 입력이 기본이다.
- 무료량 안의 개발·시연이 목표이며 실제 API와 LLM 호출량을 구분한다.
- 실제 연동 테스트와 합성 데이터 기반 재현 평가는 분리한다.
- Windows PowerShell과 macOS zsh 모두 개발·실행 대상으로 한다. 경로는 pathlib, 파일 인코딩은 UTF-8을 사용하고 OS별 절대 경로를 코드에 넣지 않는다.

## 실행 환경과 결정

현 환경: Python 3.12.5, Node 20.17.0, npm 11.5.2. 프런트엔드는 Node 22.12 이상인 22.x를 설치한 후 시작한다. 현재 Vite 문서의 요구사항은 Node 20.19+ 또는 22.12+이다. 임의로 시스템 런타임을 교체하지 말고 설치 권한을 요청한다.

Python은 uv로 관리하고 uv.lock과 web/package-lock.json을 커밋한다. Windows·macOS에서 uv sync --locked 및 npm ci로 설치한다. .python-version에는 3.12, .node-version과 .nvmrc에는 22를 기록한다. dev 의존성은 dependency-groups.dev로 선언한다.

백엔드는 1 worker로 실행한다. lifespan에서 단일 감시 루프를 시작·종료하고 SQLite에 예정 시각·이벤트·실행 상태를 저장한다. 서버 중단 후 running 실행은 interrupted로 복구하며 무조건 외부 호출을 재실행하지 않는다.

기본 실행 모드는 synthetic. 실제 연동은 APP_MODE=live와 키 설정이 모두 있을 때만 활성화한다. 모델 제공자의 키가 아직 없다면 합성 흐름을 계속 개발하고 실제 모델 연동을 완료했다고 보고하지 않는다. ModelGateway의 실제 제공자는 실행 시 사용자가 보유한 계정 기준으로 결정한다. 모델을 하드코딩하지 않는다.

초기 설정 기본값:
- 대안 목표 3, 후보 최대 9, 후보 수정 라운드 최대 3.
- 실행당 도구 물리 요청 최대 18, 모델 호출 최대 6, 전체 90초.
- 도구 timeout 8초, 일시 오류 재시도 최대 2회, 지연 0.5초·1초.
- 날씨 조회 30분 간격, 여행일 현지 08:00~22:00, 화면 상태 polling 5초.
- 활성 여행별 동시 재계획 1개, 동일 이벤트 재처리 금지.
- 제안 유효시간 10분. 선택 시 최신 위치·시간·버전으로 재검증.
- 합성 강수 시연은 60분 내 강수확률 60% 이상이며 rain_sensitive=true인 미완료 활동에 영향 이벤트를 생성한다. 이는 제품 기본 정책이고 물리적 불가능 판정이 아니다. 선호에서 민감도를 조정한다.
- 공급자별 월 차단량은 확인된 무료량의 80%로 설정한다. 미등록 SKU는 live 호출 차단. 앱 밖에서 쓴 사용량은 감지할 수 없음을 설정 화면에 명시한다.
- 비용 추정은 USD 소수로 저장하고 가격표 기준일을 기록한다. 사용자 여행 예산과 API 운영비를 분리한다.

## 파일 구조와 계약

모든 Python 패키지 디렉터리에 __init__.py를 만든다.

| 경로 | 책임 |
|---|---|
| pyproject.toml, uv.lock, .env.example, .gitignore | 환경·의존성·비밀 제외 |
| src/adaptive_trip/domain/models.py | 상태·일정·조건·제안 모델 |
| src/adaptive_trip/domain/validation.py | 시간·경로·예산·고정 조건 검증 |
| src/adaptive_trip/storage/repository.py, schema.sql | SQLite 트랜잭션·중복 방지 |
| src/adaptive_trip/tools/contracts.py, synthetic.py | 정규화 도구와 합성 제공자 |
| src/adaptive_trip/tools/google_places.py, google_routes.py, google_weather.py | 실제 제공자 매핑 |
| src/adaptive_trip/tools/budget.py, http.py, retention.py | 사용량·재시도·저장 허용 범위 |
| src/adaptive_trip/agent/contracts.py, graph.py, gateway.py, prompts.py | 도구 결정·후보 생성·검증 반복 |
| src/adaptive_trip/services/decisions.py, intake.py, monitor.py | 선택 확정·초안·변화 감시 |
| src/adaptive_trip/api/app.py, routes.py, schemas.py | HTTP·lifespan·의존성 연결 |
| src/adaptive_trip/evaluation/scenarios.py, runner.py, metrics.py | 시나리오·비교 실행·점수 |
| tests/conftest.py, tests/fixtures/ | 합성 상태와 실패 조건 |
| tests/unit/, tests/integration/, tests/e2e/ | 검증·저장·전체 흐름 |
| web/src/api.ts, types.ts, App.tsx | 서버 연결·UI 조립 |
| web/src/features/intake/, itinerary/, proposals/, feedback/ | 사용자 기능 |
| web/src/styles.css, web/e2e/travel.spec.ts | 반응형 표현·브라우저 테스트 |
| docs/architecture.md, docs/evaluation.md, docs/demo.md, docs/provider-data-policy.md | 포트폴리오 증거 |

공통 이름과 타입은 Task 1~3에서 정의한다.
- Money(amount: Decimal, currency: str, certainty: confirmed|estimated).
- Item(id, place_id, start, end, status: pending|active|completed, fixed, cost: Money|None, rain_sensitive).
- TripState(id, version, timezone, items: list[Item], position, position_at, now, spent: list[Money], constraints, travel_mode).
- Check(code, status: pass|fail|unknown, item_id, evidence_ids, message).
- Report(checks: list[Check]); eligible는 fail·unknown이 모두 없는 경우만 true.
- Candidate(id, items, rationale, signature); signature는 순서 있는 place_id와 활동 종류로 계산한다.
- Proposal(id, trip_id, base_version, created_at, expires_at, candidates, reports, status, reason).
- Observation(id, kind, status, observed_at, valid_until, source, data); data는 PlacesData·RouteData·WeatherData tagged union.
- ChangeEvent(id, trip_id, kind, at, affected_item_ids, payload, fingerprint).
- DecisionResult(status: applied|rejected|stale|needs_confirmation|invalid, state, proposal_id).
- RunResult(proposal, observations, checks, trace, tool_calls, model_calls, stop_reason).
- Scenario(state, event, observations, candidates, oracle, now). oracle에는 expected_outcome, minimum_valid_candidates, fixed_ids를 명시한다.
- scenario(name: str) -> Scenario는 tests/conftest.py의 pytest fixture가 반환하는 팩토리다. 각 테스트는 독립 deep copy를 받는다.
- db는 임시 SQLite Repository fixture, clock은 .now()·.advance(seconds)를 제공하는 FrozenClock fixture다.
- test snippets의 scenario, db, clock은 위 fixture다. import는 해당 Task의 Produces 경로에서 추가한다.

## 공통 검증과 커밋 규칙

아래 각 Task는 실패 테스트 → 실패 원인 확인 → 최소 구현 → 통과 확인 → 해당 파일만 커밋 순서다. 테스트 예제는 핵심 회귀 사례이며 추가 명시 사례도 매개변수화한다. 환경 설치 오류는 기능의 기대 실패로 간주하지 않는다. 읽기 전용 환경의 설치·파일 생성·커밋은 도구의 권한 흐름으로 처리한다.

코드 변경 후: uv run --locked python -m pytest <task test path> -q.
작업 간 통합: uv run --locked python -m pytest tests/unit tests/integration -q.
완료 시: uv run --locked python -m pytest -q, npm --prefix web run test -- --run, npm --prefix web run build, npm --prefix web exec playwright test, git diff --check.
live 테스트는 기본 pytest에서 제외하고 LIVE_TESTS=1인 명시 실행에서만 실제 API를 호출한다.


## Task 1: 상태 모델과 재현 가능한 첫 시나리오

**Files:**

- Create: pyproject.toml, uv.lock, .env.example, .gitignore, src/adaptive_trip/domain/models.py, tests/conftest.py, tests/fixtures/rain.json
- Test: tests/unit/test_models.py

**Interfaces:** Produces: 위 공통 모델; TripState.model_validate(dict), scenario(name) fixture. rain.json은 2026-09-08 14:30+09:00의 완료 점심, 15:30 야외 장소, 19:00 고정 저녁 예약, 실내 대체 후보 3개 및 각 구간 경로·영업·비용의 합성 자료를 포함한다. 실제 장소를 사칭하지 않도록 synthetic:* ID를 사용한다.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
def test_naive_time_is_rejected(scenario):
    import pytest
    from adaptive_trip.domain.models import TripState
    raw = scenario("rain").state.model_dump(mode="json")
    raw["now"] = "2026-09-08T14:30:00"
    with pytest.raises(ValueError):
        TripState.model_validate(raw)
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/unit/test_models.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
from pydantic import AwareDatetime, BaseModel, ConfigDict
class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    place_id: str
    start: AwareDatetime
    end: AwareDatetime
    status: str
    fixed: bool
    cost: Money | None = None
    rain_sensitive: bool = False
```

공통 계약의 나머지 필드도 같은 모델 파일에 정의한다. status는 Literal로 제한하고 end>start, 금액>=0, 유효 좌표·IANA 시간대를 검사한다. 금액은 Decimal, 시간대 데이터는 공통 tzdata 의존성으로 처리한다. 완료 일정 보존은 비교 검증에서 수행한다. 초기 의존성은 pydantic>=2,<3, pytest, pytest-asyncio, httpx, fastapi, uvicorn, langgraph, tzdata, python-dotenv를 설치·잠금한다. 합성 시나리오 factory는 JSON을 매 호출 읽어 모델로 생성한다. 다른 시나리오는 후속 Task에서 같은 schema로 추가한다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/unit/test_models.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: add trip state models and synthetic scenario"`를 실행한다.

## Task 2: 제약을 통과·위반·미확인으로 계산

**Files:**

- Create: src/adaptive_trip/domain/validation.py, tests/fixtures/late.json, tests/fixtures/unknown_route.json
- Test: tests/unit/test_validation.py

**Interfaces:** Consumes: TripState, Candidate, Observation. Produces: validate(state: TripState, candidate: Candidate, observations: list[Observation], now: datetime) -> Report.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
def test_unknown_route_is_not_eligible(scenario):
    from adaptive_trip.domain.validation import validate
    s = scenario("unknown_route")
    report = validate(s.state, s.candidates[0], s.observations, s.now)
    assert not report.eligible
    assert any(c.code == "route" and c.status == "unknown" for c in report.checks)
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/unit/test_validation.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
def route_status(observation, depart_at, arrive_by):
    if observation is None or observation.status != "ok":
        return "unknown"
    if observation.valid_until < depart_at:
        return "unknown"
    return "pass" if depart_at + timedelta(seconds=observation.data.duration_seconds) <= arrive_by else "fail"
```

route_status는 내부 함수다. 구간의 실제 출발 예정 시각에 해당하는 경로 결과인지 검사한다. 고정 예약·필수 장소·최종 도착·완료 항목 보존, 일정 겹침, 체류시간 전체가 영업 구간 안인지, 날짜 변경, 예산을 각각 Check로 반환한다. 자정을 넘는 영업 구간은 절대시각 구간으로 비교한다. 누락 영업시간·비용·환산 정보는 unknown이다. 필수 방문과 고정 시간은 별도 조건이다. hard 예산 위반은 fail, 선호 위반은 ranking 신호로만 반환한다. 시나리오 late는 19시 예약을 늦게 도착하는 후보를 포함한다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/unit/test_validation.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: validate itinerary constraints with explicit unknowns"`를 실행한다.

## Task 3: 정규화 도구와 외부 호출 한도

**Files:**

- Create: src/adaptive_trip/tools/contracts.py, synthetic.py, budget.py, http.py
- Test: tests/unit/test_tools.py, tests/unit/test_budget.py

**Interfaces:** Produces: ToolRequest(name, arguments, sku, units); ToolResult(observation, attempts, error_code); async ToolProvider.call(request: ToolRequest) -> ToolResult. SyntheticTools(observations) 구현. CallBudget(max_requests).reserve(units: int) -> bool. Clock.now() -> datetime, FrozenClock은 tests/conftest.py.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
def test_budget_counts_physical_requests():
    from adaptive_trip.tools.budget import CallBudget
    budget = CallBudget(max_requests=2)
    assert budget.reserve(1)
    assert budget.reserve(1)
    assert not budget.reserve(1)
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/unit/test_tools.py tests/unit/test_budget.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
def reserve(self, units: int) -> bool:
    if units < 1:
        raise ValueError("units must be positive")
    if self.used + units > self.max_requests:
        return False
    self.used += units
    return True
```

CallBudget에 used=0을 둔다. 동시 실제 호출의 월 사용량 예약은 Task 4의 DB 트랜잭션으로 이동한다. 재시도 전에 매번 물리 요청 예산을 차감한다. 경로 행렬 units는 출발지 수×도착지 수다. 429·5xx·연결 timeout만 최대 2회 재시도하고 400·401·403은 즉시 구조화 오류를 반환한다. HTTP sleep과 시계는 주입해 테스트에서 실제 대기하지 않는다. ToolRequest는 허용 이름 places_search, place_details, route, weather 및 각 인자 모델로 검증한다. 합성 공급자는 준비된 응답만 반환하며 알 수 없는 요청은 missing이다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/unit/test_tools.py tests/unit/test_budget.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: add bounded tool interface and synthetic provider"`를 실행한다.

## Task 4: SQLite 상태 저장과 버전 경쟁 처리

**Files:**

- Create: src/adaptive_trip/storage/schema.sql, repository.py
- Modify: tests/conftest.py
- Test: tests/integration/test_repository.py

**Interfaces:** Produces: Repository(path).create(state), get(trip_id)->TripState, save_proposal(proposal), get_proposal(id)->Proposal, compare_and_swap(state, expected_version)->bool, reserve_usage(sku, month, units, limit)->bool. decision_requests는 (trip_id,request_id) unique. notifications·events·runs·usage·drafts 테이블도 schema에 정의한다.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
def test_stale_write_cannot_overwrite_state(db, scenario):
    state = scenario("rain").state
    db.create(state)
    newer = state.model_copy(update={"version": state.version + 1})
    assert db.compare_and_swap(newer, expected_version=state.version)
    assert not db.compare_and_swap(newer, expected_version=state.version)
    assert db.get(state.id).version == state.version + 1
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/integration/test_repository.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
cursor = connection.execute(
    "UPDATE trips SET version=?, state_json=? WHERE id=? AND version=?",
    (state.version, state.model_dump_json(), state.id, expected_version),
)
return cursor.rowcount == 1
```

트랜잭션은 BEGIN IMMEDIATE로 시작하고 commit/rollback을 보장한다. 상태 version은 쓰기마다 1 증가한다.SQL은 매개변수화한다. 모드 활성화·상태 이벤트·확정 선택도 동일한 버전 규칙을 쓴다. read-modify-write 경쟁과 중복 이벤트 fingerprint unique를 테스트한다. usage 예약은 남은 한도를 같은 transaction에서 확인한다. DB에는 사용자 상태·제안의 사용자 결정 정보와 실행 메타데이터를 저장하며 공급자 원문 저장은 Task 7의 정책을 따른다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/integration/test_repository.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: persist versioned trips and bounded usage"`를 실행한다.

## Task 5: 기본 3개 대안을 만드는 제한된 Agent 흐름

**Files:**

- Create: src/adaptive_trip/agent/contracts.py, graph.py, gateway.py, prompts.py
- Create: tests/fixtures/two_alternatives.json, tests/fixtures/impossible.json
- Test: tests/unit/test_graph.py

**Interfaces:** Produces: AgentAction(kind: tool|candidates|stop, request: ToolRequest|None, candidates: list[Candidate], reason: str). ModelGateway.next(context: dict)->AgentAction (async). ScriptedGateway(actions) implements this for tests. Replanner(model, tools, limits).run(state, event, observations, now)->RunResult (async).

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
async def test_replan_keeps_original_and_offers_three(scenario):
    from adaptive_trip.agent.graph import Replanner
    from adaptive_trip.agent.gateway import ScriptedGateway
    from adaptive_trip.agent.contracts import AgentAction
    from adaptive_trip.tools.synthetic import SyntheticTools
    s = scenario("rain")
    original = s.state.model_dump_json()
    planner = Replanner(
        ScriptedGateway([AgentAction(kind="candidates", candidates=s.candidates, reason="실내 대안")]),
        SyntheticTools(s.observations),
        limits={"rounds": 3, "tool_calls": 18, "model_calls": 6},
    )
    result = await planner.run(s.state, s.event, s.observations, s.now)
    assert len(result.proposal.candidates) == 3
    assert s.state.model_dump_json() == original
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/unit/test_graph.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
def choose_next(context):
    if context["deadline_reached"] or context["budget_exhausted"]:
        return "finish"
    if len(context["eligible"]) >= 3:
        return "finish"
    if context["rounds"] >= context["max_rounds"]:
        return "finish"
    return "decide"
```

StateGraph 노드는 decide, call_tool, validate, finish다. AgentAction으로 조건 분기하고 후보 수정 라운드는 validate 통과마다 증가시킨다. 모델 호출과 tool 호출·벽시계 한도를 별도로 적용한다. 매 호출에 고정 조건, 확정 상태, 확인된 관측, 직전 검증 오류를 제공한다. candidate signature로 중복을 제거하고 최대 9개 중 통과한 3개를 선택한다. two_alternatives는 2개와 부족 이유, impossible은 0개와 충돌 설명을 반환해야 한다. 정책에 맞지 않는 도구 요청·형식 오류도 호출 한도 안에서 종료한다. trace는 노드·action·검증 결과만 기록하고 숨겨진 추론 텍스트를 요구하지 않는다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/unit/test_graph.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: orchestrate validated alternatives with bounded replanning"`를 실행한다.

## Task 6: 선택·거절·오래된 제안 처리

**Files:**

- Create: src/adaptive_trip/services/decisions.py
- Modify: src/adaptive_trip/storage/repository.py
- Test: tests/integration/test_decisions.py

**Interfaces:** Produces: async DecisionService(repo, tools, clock).decide(trip_id, proposal_id, candidate_id: str|None, action: accept|reject, request_id: str)->DecisionResult. Repository.atomic_decision(...)은 decision_requests 중복 조회, version CAS, 결정 기록을 단일 트랜잭션에서 수행한다.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
async def test_accept_is_idempotent(decision_service, pending_proposal):
    p = pending_proposal
    first = await decision_service.decide(p.trip_id, p.id, p.candidates[0].id, "accept", "choice-1")
    again = await decision_service.decide(p.trip_id, p.id, p.candidates[0].id, "accept", "choice-1")
    assert first.status == "applied"
    assert again.state.version == first.state.version
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/integration/test_decisions.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
if stored_decision is not None:
    return stored_decision
if state.version != proposal.base_version or now >= proposal.expires_at:
    return DecisionResult(status="stale", state=state, proposal_id=proposal.id)
if not report.eligible:
    return DecisionResult(status="needs_confirmation", state=state, proposal_id=proposal.id)
```

tests/conftest.py에 rain 시나리오로 생성·저장한 pending_proposal 및 FrozenClock과 SyntheticTools를 주입한 decision_service fixture를 추가한다. 네트워크 재검증은 DB lock 밖에서 실행하고 마지막 write 시 version을 다시 확인한다. reject는 proposal 상태만 변경하고 일정 version·내용은 유지한다. 고정 조건 완화는 별도 확인된 사용자 조건 변경 이벤트 이후 새 제안 생성으로 처리한다. stale은 자동 적용하지 않고 최신 상태의 새로운 제안을 사용자에게 보여준다. 다른 여행의 proposal_id·존재하지 않는 후보도 invalid 처리한다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/integration/test_decisions.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: apply user decisions atomically without stale overwrites"`를 실행한다.

## Task 7: Google 도구와 공급자 데이터 정책 연결

**Files:**

- Create: src/adaptive_trip/tools/google_places.py, google_routes.py, google_weather.py, retention.py
- Create: docs/provider-data-policy.md, tests/fixtures/google_synthetic.json
- Test: tests/unit/test_google_tools.py, tests/integration/test_google_live.py

**Interfaces:** Consumes ToolProvider, ToolRequest, ToolResult. Produces GoogleTools(http_client, usage_repo, settings).call(request)->ToolResult; retention.allowed_fields(source, purpose)->set[str]. google_synthetic.json은 공식 응답 schema에 맞춘 자체 작성 자료다.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
async def test_missing_opening_hours_remain_unknown(google_tools):
    from adaptive_trip.tools.contracts import ToolRequest
    result = await google_tools.call(ToolRequest(
        name="place_details", arguments={"place_id": "synthetic:missing-hours"},
        sku="place_details_enterprise", units=1,
    ))
    assert result.observation.data.opening_intervals is None
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/unit/test_google_tools.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
FIELD_MASK = "id,displayName,location,currentOpeningHours"
response = await client.get(
    "https://places.googleapis.com/v1/places/" + place_id,
    headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK},
)
payload = response.json()
```

google_tools fixture는 httpx.MockTransport로 합성 JSON을 반환한다. live place_id는 검증·인코딩 후 URL 경로에 넣는다. 필드별 과금 등급을 SKU에 매핑하고 현재 공식 표를 다시 확인한다. nearby/text search에서 후보 ID를 얻고 필요한 후보만 details로 확인한다. routes는 출발시간 기준 구간별 computeRoutes를 호출하며 대중교통 중간 경유지를 한 요청으로 지원한다고 가정하지 않는다. 날씨는 대상 좌표·현지 일정 시간의 forecast를 조회한다. 누락 요금·시간·미지원 지역은 정규화 상태로 반환한다. Google 정책 문서에서 영구 저장 가능 필드·기간·attribution을 필드별 표로 확인하고, 미확인 필드는 영구 저장하지 않는다. place ID·사용자 입력 일정과 공급자 원문을 분리한다. 화면은 Google attribution을 표시하고 Google 데이터의 지도 표시는 Google 지도를 사용할 때만 추가한다. 키는 server only. 실연동은 사용자 확인 가능한 서울·오사카·후쿠오카 좌표의 최소 요청으로 검증한다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/unit/test_google_tools.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: integrate Google tools with explicit data provenance"`를 실행한다.

## Task 8: 실제 모델 도구 호출 및 구조화 응답

**Files:**

- Modify: src/adaptive_trip/agent/gateway.py, prompts.py
- Create: tests/fixtures/model_responses.json
- Test: tests/unit/test_model_gateway.py, tests/integration/test_model_live.py

**Interfaces:** Produces: LiveModelGateway(client, model_id).next(context)->AgentAction. client는 선택된 공급자 SDK를 감싼 request(messages, tools, response_schema) async 계약이다. Task 5의 ScriptedGateway와 동일 결과를 반환한다.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
async def test_invalid_tool_name_does_not_execute(live_gateway, tool_spy):
    action = await live_gateway.next({"event": "rain", "state_version": 1})
    assert action.kind == "stop"
    assert tool_spy.calls == []
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/unit/test_model_gateway.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
try:
    action = AgentAction.model_validate(provider_output)
except ValueError:
    return AgentAction(kind="stop", candidates=[], reason="invalid_model_response")
return action
```

live_gateway fixture는 허용되지 않은 tool 이름을 응답하는 가짜 client다. 실제 제공자 선정 후 해당 공식 tool-calling·structured-output 문서를 읽고 SDK 응답을 provider_output으로 매핑한다. 모델 ID는 MODEL_ID, 키는 해당 공급자 환경 변수로 받는다. tool schema는 ToolRequest 인자 모델에서 생성한다. 모델 텍스트가 외부 호출을 직접 실행하지 않는다. 장소 설명의 지시문은 untrusted_data로 전달하고 모델이 완료 일정이나 고정 조건을 바꾸어도 validator가 거부하는 회귀 사례를 둔다. token usage와 실제 제공자가 보고한 model ID를 기록한다. live 모델 호출은 explicit flag로만 수행하며 기본 CI는 mock이다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/unit/test_model_gateway.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: connect structured model decisions to the tool workflow"`를 실행한다.

## Task 9: 일정 입력·생성과 HTTP 상태 API

**Files:**

- Create: src/adaptive_trip/services/intake.py, src/adaptive_trip/api/app.py, routes.py, schemas.py
- Test: tests/integration/test_api.py, tests/unit/test_intake.py

**Interfaces:** Produces: create_app(settings, repo, replanner, tools, clock)->FastAPI. IntakeService.prepare(text: str|None, preferences: dict)->Draft (async), confirm(draft_id, confirmed_fields, request_id)->TripState. Draft(id, items, questions, assumptions, confirmed). 서버 DTO는 Pydantic에서 OpenAPI로 생성한다.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
def test_unresolved_draft_cannot_be_confirmed(api_client):
    draft = api_client.post("/api/drafts", json={"text": "내일 미술관 갔다가 저녁"}).json()
    response = api_client.post("/api/drafts/" + draft["id"] + "/confirm",
                               json={"confirmed_fields": {}, "request_id": "draft-1"})
    assert response.status_code == 422
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/integration/test_api.py tests/unit/test_intake.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
@router.get("/trips/{trip_id}")
def get_trip(trip_id: str):
    return repo.get(trip_id)

@router.post("/trips/{trip_id}/decisions")
async def decide(trip_id: str, body: DecisionInput):
    return await decisions.decide(trip_id, **body.model_dump())
```

api_client fixture는 합성 공급자·스크립트 모델·임시 DB를 가진 TestClient다. API: POST /api/drafts, POST /api/drafts/{id}/confirm, GET /api/trips/{id}, POST /api/trips/{id}/events, GET /api/trips/{id}/proposals, POST /api/trips/{id}/decisions, PATCH /api/trips/{id}/mode. DTO DecisionInput은 Task 6 인자에서 trip_id를 제외한다. EventInput은 kind·payload·expected_version·request_id를 포함한다. POST events는 상태 갱신 후 202/run_id를 반환하고 작업 상태는 GET /api/runs/{id}로 확인한다. 지연·완료·지출·위치·선호·고정 조건 변경은 검증된 이벤트로 표현한다. 새 일정 생성도 Draft 확인을 거친다. 모호한 장소의 질문, 체류시간 추정 표시, 다일 일정과 시간대 유지가 필요하다. 404/409/422/503을 구분한다. 최초 기본은 localhost 단일 사용자 앱이다. 공개 배포 인증은 별도 범위 결정 전 추가하지 않으며 공개에 노출하지 않는다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/integration/test_api.py tests/unit/test_intake.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: expose draft confirmation and travel state APIs"`를 실행한다.

## Task 10: 주기 날씨 감시와 선제 알림

**Files:**

- Create: src/adaptive_trip/services/monitor.py
- Modify: src/adaptive_trip/api/app.py, routes.py, src/adaptive_trip/storage/repository.py
- Test: tests/integration/test_monitor.py

**Interfaces:** Produces: Monitor(repo, tools, replanner, clock, settings).tick()->list[str] (async); returned strings는 생성한 event ID다. GET /api/trips/{id}/notifications와 run/proposal polling 지원. Repository.active_due_trips(now), claim_event(event)->bool, update_next_check(id,at), interrupt_running_runs().

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
async def test_repeated_forecast_does_not_duplicate_alerts(monitor, clock):
    first = await monitor.tick()
    clock.advance(1800)
    second = await monitor.tick()
    assert len(first) == 1
    assert second == []
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/integration/test_monitor.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
fingerprint = f"{trip.id}:{local_date}:{item.id}:rain:{forecast_window}"
if repo.claim_event(event.model_copy(update={"fingerprint": fingerprint})):
    await replanner.run(trip, event, observations, clock.now())
```

monitor fixture에는 활성 여행 1개와 동일한 rain forecast를 주입한다. tick은 due 여행만 처리하고 다음 조회를 persist한다. 날씨 조회는 실제 관련 위치별로 묶고 월 예산을 먼저 예약한다. 일정 영향 없으면 모델을 호출하지 않는다. 비 민감도 변경·예보 시간대의 실질 변화·영향 항목 변경을 새 이벤트로 다루되, 같은 이벤트 거절 후 반복 제안하지 않는다. 앱 lifespan에서 asyncio task를 시작·취소하고 shutdown 완료를 기다린다. 서버 재시작은 due 시각을 복구하고 running을 interrupted로 변경해 상태 오염을 방지한다. 화면 닫힘과 관계없이 서버가 켜진 동안 tick은 진행하며 모바일 push로 표현하지 않는다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/integration/test_monitor.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: proactively monitor travel changes without duplicate alerts"`를 실행한다.

## Task 11: 일정표·3개 대안·피드백 화면

**Files:**

- Create: web/package.json, package-lock.json, index.html, vite.config.ts, tsconfig.json, src/main.tsx, src/App.tsx, src/api.ts, src/types.ts, src/styles.css
- Create: web/src/features/intake/Intake.tsx, itinerary/Timeline.tsx, proposals/ProposalList.tsx, feedback/Feedback.tsx
- Test: web/src/features/proposals/ProposalList.test.tsx, web/e2e/travel.spec.ts

**Interfaces:** Consumes Task 9 HTTP JSON. Produces React 화면. ProposalList({proposal,onAccept,onReject,onRefine})는 후보별 button과 검증 정보를 표시한다. types.ts는 backend OpenAPI에서 생성하고 JSON datetime은 ISO 문자열, 금액은 decimal string으로 처리한다.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```tsx
it("shows three alternatives and preserves the original until selection", async () => {
  render(<ProposalList proposal={threeChoiceProposal} onAccept={accept}
    onReject={reject} onRefine={refine} />);
  expect(screen.getAllByRole("button", {name: "이 대안 선택"})).toHaveLength(3);
  expect(accept).not.toHaveBeenCalled();
});
```

- [ ] **2. 기대 실패 확인.** `npm --prefix web run test -- --run`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```tsx
return <section aria-label="대안 비교">
  {proposal.candidates.map(candidate =>
    <article key={candidate.id}>
      <h3>{candidate.title}</h3>
      <p>{candidate.rationale}</p>
      <button onClick={() => onAccept(candidate.id)}>이 대안 선택</button>
    </article>
  )}
</section>;
```

UI DTO는 Candidate의 id·rationale에 title, 변경 비교와 report를 결합한 CandidateView다. 테스트에 threeChoiceProposal을 합성 모델에 맞춰 로컬 상수로 정의하고 accept/reject/refine는 vi.fn()이다. Node 업그레이드 후 React TS Vite 템플릿을 생성한다. 화면은 시작 선택, 입력·질문 확인, 일정표, 변화 알림, 대안 비교, 피드백 순서다. desktop 3열·mobile 1열, 키보드 버튼·label·오류 안내를 제공한다. 거리·시간·비용·통화·고정 조건·unknown·attribution을 카드에 표시한다. 1~2개 부족 이유, 0개 충돌, loading, API 오류, stale 재확인, 거절 시 원본 유지, polling 재접속을 다룬다. 개발용 시뮬레이션 이벤트 버튼은 APP_MODE=synthetic에서만 제공한다. 지도는 필수 동선이 아니므로 첫 UI는 일정표·비교 중심으로 완성한다.

- [ ] **4. 검증.** `npm --prefix web run test -- --run`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "feat: build travel timeline and three-alternative feedback UI"`를 실행한다.

## Task 12: 비교 평가·전체 시연·포트폴리오 문서

**Files:**

- Create: src/adaptive_trip/evaluation/scenarios.py, runner.py, metrics.py, docs/evaluation.md, docs/demo.md, docs/architecture.md, README.md
- Create: tests/fixtures/scenarios.json
- Test: tests/unit/test_metrics.py, tests/e2e/test_scenarios.py
- Modify: web/e2e/travel.spec.ts

**Interfaces:** Produces: score(checks:list[Check])->dict; evaluate(scenarios, strategies, repetitions, seed)->dict (async); uv run --locked python -m adaptive_trip.evaluation.runner --mode synthetic --repetitions 3 --output results/evaluation.json. strategies: single_pass, informed_single_pass, agent, informed_full, agent_full.

- [ ] **1. 실패 테스트 작성.** 다음 핵심 회귀 사례를 테스트 파일에 작성한다.

```python
def test_unknown_counts_against_fulfilment():
    from adaptive_trip.domain.models import Check
    from adaptive_trip.evaluation.metrics import score
    checks = [
        Check(code="fixed", status="pass", item_id="a", evidence_ids=[], message="ok"),
        Check(code="route", status="unknown", item_id="b", evidence_ids=[], message="missing"),
    ]
    assert score(checks)["constraint_fulfilment"] == 0.5
```

- [ ] **2. 기대 실패 확인.** `uv run --locked python -m pytest tests/unit/test_metrics.py tests/e2e/test_scenarios.py -q`를 실행한다. 아직 정의되지 않은 모듈·동작으로 실패하는지 확인한다. 환경 오류이면 환경을 수정한 뒤 다시 확인한다.

- [ ] **3. 최소 구현.** 다음 핵심 분기와 상세 규칙을 지정 파일에 구현한다.

```python
def score(checks):
    counts = {name: sum(c.status == name for c in checks)
              for name in ("pass", "fail", "unknown")}
    total = len(checks)
    return {**counts, "constraint_fulfilment": counts["pass"] / total if total else None}
```

scenarios.json은 rain, delay, closed, preference, reservation_conflict, timeout, missing_data, impossible, two_alternatives, stale_choice, duplicate_choice를 정의한다. 실제 도시는 서울·오사카·후쿠오카 별도 live smoke로 다루고 미지원은 품질 제한으로 기록한다. 각 scenario의 oracle는 단일 정답 일정 대신 적용 제약·가능 후보 수·기대 종료 상태를 명시한다. 모든 전략에 같은 model ID·원본 상태·변화·실행 예산을 적용한다. single_pass는 초기 도구 자료 없음, informed_single_pass·agent는 동일 초기 관측, informed_full·agent_full은 모든 동일 관측을 받아 추가 정보 효과를 분리한다. single pass는 3개 후보를 한 호출에 요청하고 같은 외부 validator로 채점한다. 제약 충족·미확인·불필요 변경·상태 보존·3개 제공 여부·p50/p95 지연·비용을 기록한다. synthetic gateway 평가는 로직 검증이며 LLM 성능 입증으로 표시하지 않는다. 실제 모델 비교는 별도 명시 실행 결과를 보고한다. 브라우저 E2E는 입력→비 이벤트→3개→거절→선호 수정→선택→새로고침 상태 유지와 stale 선택을 포함한다. README에 설치·synthetic/live 구분·아키텍처·평가 재현·실측 한계·시연 절차를 작성한다.

- [ ] **4. 검증.** `uv run --locked python -m pytest tests/unit/test_metrics.py tests/e2e/test_scenarios.py -q`를 다시 실행하여 PASS를 확인한다. 상세 규칙에 명시된 실패 사례도 매개변수화해 같은 테스트 파일에서 검증한다.
- [ ] **5. 변경 검토·커밋.** `git diff --check`와 `git diff --stat`를 확인하고 이 작업의 Files에 해당하는 경로만 `git add -- <해당 경로>`로 stage한다. `git diff --cached --check` 성공 후 `git commit -m "test: evaluate adaptive replanning and document reproducible demo"`를 실행한다.

## Task 13: Windows·macOS 개발 환경과 CI

**Files:**

- Create: .github/workflows/ci.yml, .python-version, .node-version, .nvmrc, .gitattributes, src/adaptive_trip/settings.py, tests/unit/test_portability.py
- Modify: README.md, docs/demo.md, web/playwright.config.ts

**Interfaces:** data_dir(base: Path|None=None)->Path. APP_DATA_DIR가 있으면 우선하며 기본은 저장소 .local이다. DB·결과 경로는 이 함수를 사용한다.

- [ ] **1. 실패 테스트 작성.**

~~~python
def test_unicode_and_spaces_in_path(tmp_path):
    from adaptive_trip.settings import data_dir
    path = data_dir(tmp_path / "여행 프로젝트") / "sample.json"
    path.write_text('{"city":"후쿠오카"}', encoding="utf-8")
    assert "후쿠오카" in path.read_text(encoding="utf-8")
~~~

- [ ] **2. 실패 확인.** uv run --locked python -m pytest tests/unit/test_portability.py -q로 미구현 함수 실패를 확인한다.
- [ ] **3. 구현.**

~~~python
from pathlib import Path
import os

def data_dir(base: Path | None = None) -> Path:
    configured = os.environ.get("APP_DATA_DIR")
    root = Path(configured) if configured else (
        base if base is not None else Path(__file__).resolve().parents[2] / ".local"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root
~~~

각 OS에서 동일한 환경을 생성한다. .python-version=3.12, .node-version 및 .nvmrc=22. Node가 22.12 이상인지 확인한다. .gitattributes는 '* text=auto'와 소스·문서별 'text eol=lf'를 선언한다. OS별 가상환경 경로를 직접 실행하지 않고 uv run을 사용한다. subprocess는 인자 배열과 sys.executable을 사용하고 shell=True에 의존하지 않는다. 임시 파일은 pytest tmp_path를 쓰고 handle을 닫은 뒤 삭제한다.

CI job은 아래 matrix로 구성하며 checkout·Python 3.12·Node 22·uv setup을 실행 단계 앞에 추가한다. action 버전은 작성 시 공식 문서로 확인하고 고정한다.

~~~yaml
strategy:
  fail-fast: false
  matrix:
    os: [windows-latest, macos-latest]
runs-on: ${{ matrix.os }}
steps:
  - run: uv sync --locked
  - run: uv run --locked python -m pytest -q
  - run: npm ci
    working-directory: web
  - run: npm run test -- --run
    working-directory: web
  - run: npm run build
    working-directory: web
  - run: npx playwright install chromium
    working-directory: web
  - run: npx playwright test
    working-directory: web
~~~

Task 1에서는 Python CI만 실행하고 web 생성 후 UI 단계를 활성화한다. 모든 기본 CI는 synthetic이며 API 키가 필요 없다. 공개 저장소·원격 CI 실행이 아직 없다면 workflow 작성과 실제 원격 실행 결과를 구분해 보고한다.

README에는 Windows에서 Git commit → Mac에서 clone/pull → uv sync --locked → npm --prefix web ci → 장비별 .env 설정 순서로 안내한다. .venv·node_modules·키는 복사하거나 커밋하지 않는다. SQLite 여행 데이터는 장비별 로컬이며 코드 이동만으로 동기화되지 않는다고 명시한다.

공통 실행은 별도 터미널에서 아래 명령을 사용한다. create_app은 인자가 생략되면 환경 설정으로 의존성을 구성하도록 optional 인자를 지원한다.

~~~text
uv run --locked uvicorn adaptive_trip.api.app:create_app --factory --host 127.0.0.1 --port 8000
npm --prefix web run dev
~~~

- [ ] **4. 검증.** Windows·macOS CI에서 Python·UI·브라우저 테스트 및 build를 확인한다. Windows 로컬 결과로 macOS 통과를 주장하지 않는다. 사용자 MacBook의 CPU 종류 확인 후 해당 장비에서도 설치·실행 smoke를 수행한다.
- [ ] **5. 커밋.** 명시된 변경 파일을 stage하고 git diff --cached --check 성공 후 git commit -m "ci: verify Windows and macOS workflows"를 실행한다.

## 단계별 실행과 요구사항 연결

Task 1~6: 합성 데이터로 재계획→3개 대안→선택 확정의 동작 가능한 핵심.
Task 7~8: 실제 도구·모델 연동. 이미 동작하는 합성 모드는 유지.
Task 9~11: 일정 입력·생성, 주기 변화 확인, 사용자 화면의 완결된 제품 흐름.
Task 12: 비교 평가와 포트폴리오 증거.
Task 13: Windows·macOS 환경 검증. CI는 Task 1부터 도입하고 web 작업 이후 검증 범위를 확대한다.

| 설계 요구사항 | 구현 작업 |
|---|---|
| 국내외 입력·시간대·다일 일정 | 1, 7, 9 |
| 기존 일정·새 일정·모호한 정보 확인 | 9, 11 |
| 시간·예산·완료·고정 조건 | 1, 2, 6 |
| 현재 상태·사실·관측·미확정 제안 분리 | 1, 4, 6 |
| Tool Calling·검증 실패 후 재계획 | 3, 5, 7, 8 |
| 기본 3개 대안·부족·충돌 설명 | 5, 11, 12 |
| 선택·거절·추가 선호·오래된 선택 | 6, 9, 11 |
| 먼저 감지·알림·중복 억제·재접속 | 10, 11 |
| API 실패·월 비용 차단·출처·미지원 | 3, 4, 7 |
| 화면과 평가 | 11, 12 |

## 구현 시 실행 명령

Python 환경은 Task 1에서 uv로 생성한다. uv 설치 안내만 Windows PowerShell과 macOS zsh용으로 나누고 이후 명령은 공통이다.

~~~text
uv python install 3.12
uv lock
uv sync --locked
uv run --locked python -m pytest tests/unit/test_models.py -q
~~~

새 장비에서는 커밋된 uv.lock으로 uv sync --locked를 실행한다. pyproject.toml은 setuptools src layout과 pytest asyncio_mode=auto를 설정한다. .gitignore에 .venv/, .env, __pycache__/, .pytest_cache/, web/node_modules/, web/dist/, .local/, 실제 공급자 응답을 추가한다. .gitattributes로 소스·Markdown·JSON·YAML 파일의 줄바꿈을 LF로 통일한다.

Task 11에서 Node 22.12+의 22.x를 사용한다. web 디렉터리가 없음을 확인한 후 생성한다.

~~~powershell
npm create vite@latest web -- --template react-ts --no-interactive
npm --prefix web install
npm --prefix web install -D vitest jsdom @testing-library/react @testing-library/jest-dom @playwright/test openapi-typescript
~~~

package.json에 test=vitest, build=tsc -b && vite build, dev=vite를 설정한다. playwright 설정은 web/e2e 경로와 합성 백엔드·Vite webServer를 지정한다. types.ts 생성 입력은 API OpenAPI JSON이며 생성 과정을 README에 명시한다. 브라우저 설치는 Task 11에서만 필요하며 권한을 받아 npm --prefix web exec playwright install chromium을 실행한다.

## 최종 검증

- [ ] Windows·macOS CI에서 설치·테스트·build 통과.
- [ ] 전체 unit/integration/E2E의 필수 상태·제약 시나리오 통과.
- [ ] synthetic 모드가 키 없이 네트워크 API를 호출하지 않고 동작.
- [ ] 실제 지도·날씨 최소 smoke 결과를 지역별로 기록. 실패·미지원은 숨기지 않음.
- [ ] 실제 모델 도구 호출과 검증 수정 trace를 최소 1개 확보.
- [ ] 동일 조건의 비교 평가를 반복 실행하고 결과와 모델·가격표 기준일 기록.
- [ ] 기본 3개 후보와 유효 후보 부족 시나리오 모두 브라우저 검증.
- [ ] git diff --check와 프런트 build 통과, 변경 파일 검토.
- [ ] README의 설치·시연 명령을 새 환경 또는 깨끗한 의존성 설치에서 재현.
- [ ] API 키·사용자 원문·허용되지 않은 공급자 데이터가 추적 파일에 없는지 확인.

## 공식 기술 근거

2026-09-08 조회. 라이브 API 구현 시 세부 계약·요금·저장 조건은 다시 확인한다.

- [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/): 잠금 파일 기반 환경 재현.
- [uv project structure](https://docs.astral.sh/uv/concepts/projects/layout/): 프로젝트·잠금 파일 구성.
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/): 서버 시작·종료 자원 관리에 사용.
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview): 결정적 처리와 Agent 판단을 같은 그래프에 결합.
- [Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/): 상태·입력 모델 검증.
- [Vite guide](https://vite.dev/guide/): 프런트 런타임 요구사항과 React TS 템플릿.
- [Google Places policies](https://developers.google.com/maps/documentation/places/web-service/policies): 저장·표시·출처 정책.
- [Google Routes policies](https://developers.google.com/maps/documentation/routes/policies): 경로 데이터 사용·표시 정책.
- Google 세부 API와 가격 문서는 승인된 Spec의 공식 참고 자료를 따른다.

## 자체 검토

- 설계의 전체 요구사항을 작업에 연결하고 추가된 Windows·macOS 호환성은 Task 13에 연결했다.
- 모델 공급자·키 선택은 실제 연동의 외부 의존성이다. 키가 없어도 합성 모드·화면·검증 개발은 가능하지만 live Agent 완료 조건은 충족되지 않는다.
- 제안 대기 상태는 SQLite에 저장하고 LangGraph checkpoint와 이중으로 확정 상태를 관리하지 않는다.
- 코드 예제는 핵심 분기이며, 완성된 구현 코드나 실행된 테스트 결과가 아니다.
- 도구 응답 저장 정책과 실측 비교는 각각 Task 7·12의 완료 조건이다.

## 실행 인계

이 계획은 실행 가능한 작업 목록이며 현재 구현된 기능은 없다. 기본 진행은 executing-plans를 사용한 현재 세션 순차 실행이다. 사용자가 병렬 위임을 선택하면 subagent-driven-development를 적용한다. 다음 시작점은 Task 1~3이며, 합성 상태·검증·도구의 첫 동작을 만든다.
