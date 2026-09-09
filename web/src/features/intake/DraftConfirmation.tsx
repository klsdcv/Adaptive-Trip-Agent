import { useState } from "react";

import type { ConfirmedDraftFields, Draft } from "../../types";

interface DraftConfirmationProps {
  draft: Draft;
  loading: boolean;
  onConfirm: (fields: ConfirmedDraftFields) => Promise<void>;
}

export function DraftConfirmation({ draft, loading, onConfirm }: DraftConfirmationProps) {
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [title, setTitle] = useState(draft.source_text);
  const [placeQuery, setPlaceQuery] = useState(draft.source_text);
  const [activityType, setActivityType] = useState("sightseeing");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [fixed, setFixed] = useState(false);
  const [rainSensitive, setRainSensitive] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const parsedLatitude = Number(latitude);
    const parsedLongitude = Number(longitude);
    if (!timezone || !latitude || !longitude || !title.trim() || !placeQuery.trim() || !start || !end) {
      setError("시간대, 위치, 장소와 방문 시간을 모두 입력해 주세요.");
      return;
    }
    if (!Number.isFinite(parsedLatitude) || !Number.isFinite(parsedLongitude)) {
      setError("위도와 경도는 숫자로 입력해 주세요.");
      return;
    }
    if (end <= start) {
      setError("종료 시간은 시작 시간보다 늦어야 합니다.");
      return;
    }
    setError("");
    await onConfirm({
      timezone,
      search_origin: { latitude: parsedLatitude, longitude: parsedLongitude },
      items: [{
        title: title.trim(),
        place_query: placeQuery.trim(),
        activity_type: activityType.trim() || "sightseeing",
        start,
        end,
        fixed,
        rain_sensitive: rainSensitive,
      }],
    });
  }

  return <section className="draft">
    <h2>일정 초안 확인</h2>
    <p>{draft.source_text}</p>
    {draft.questions.map((question) => <p key={question}>확인: {question}</p>)}
    <form className="draft-fields" onSubmit={submit}>
      <label>시간대<input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Seoul" /></label>
      <div className="coordinate-fields">
        <label>위도<input inputMode="decimal" value={latitude} onChange={(event) => setLatitude(event.target.value)} placeholder="37.5665" /></label>
        <label>경도<input inputMode="decimal" value={longitude} onChange={(event) => setLongitude(event.target.value)} placeholder="126.9780" /></label>
      </div>
      <label>표시할 일정 이름<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <label>Google에서 찾을 장소<input value={placeQuery} onChange={(event) => setPlaceQuery(event.target.value)} /></label>
      <label>활동 종류<input value={activityType} onChange={(event) => setActivityType(event.target.value)} /></label>
      <div className="time-fields">
        <label>시작 시간<input type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} /></label>
        <label>종료 시간<input type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
      </div>
      <div className="check-fields">
        <label><input type="checkbox" checked={fixed} onChange={(event) => setFixed(event.target.checked)} /> 예약·고정 일정</label>
        <label><input type="checkbox" checked={rainSensitive} onChange={(event) => setRainSensitive(event.target.checked)} /> 비에 영향받는 일정</label>
      </div>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={loading}>{loading ? "장소 확인 중…" : "장소 확인 후 여행 확정"}</button>
    </form>
  </section>;
}
