# Adaptive Trip Agent

상태 변화에 맞춰 여행 일정을 다시 검증하고 대안을 제안하는 여행 플래너입니다.

## 빠른 시작

```powershell
& .venv\Scripts\python.exe -m pytest -q
npm --prefix web install
npm --prefix web run dev
```

백엔드는 `src/adaptive_trip/api/runtime.py`로 실행하며, 기본 synthetic 모드에서는 외부 API 키 없이 동작합니다. 실연동은 `.env`에 서버 전용 키를 넣고 runtime 설정을 확인하세요.

## 주요 흐름

1. 자연어 일정 입력 → 초안 질문·가정 확인
2. 장소 검색 및 시간대가 포함된 일정 확정
3. 날씨·지연·휴무·완료·피로·위치 이벤트 수신
4. 현재 상태를 검증한 뒤 최대 3개 대안 제안
5. 사용자가 선택하기 전까지 원래 일정을 보존

평가 실행:

```powershell
& .venv\Scripts\python.exe -m adaptive_trip.evaluation.runner --mode synthetic --repetitions 3 --output results/evaluation.json
```

자세한 실행 방법은 [docs/demo.md](docs/demo.md), 구조는 [docs/architecture.md](docs/architecture.md)를 참고하세요.
