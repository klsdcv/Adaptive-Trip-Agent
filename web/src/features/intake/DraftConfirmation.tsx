import { useState } from "react";

import type { ConfirmedDraftFields, Draft, DraftItem } from "../../types";

interface DraftConfirmationProps {
  draft: Draft;
  loading: boolean;
  onConfirm: (fields: ConfirmedDraftFields) => Promise<void>;
}

export function DraftConfirmation({ draft, loading, onConfirm }: DraftConfirmationProps) {
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [items, setItems] = useState<DraftItem[]>(draft.items.length ? draft.items : [{
    id: "manual-item",
    title: draft.source_text,
    place_query: draft.source_text,
    activity_type: "sightseeing",
    start: null,
    end: null,
    fixed: false,
    rain_sensitive: false,
  }]);
  const [error, setError] = useState("");

  function updateItem(index: number, update: Partial<DraftItem>) {
    setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...update } : item));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const parsedLatitude = Number(latitude);
    const parsedLongitude = Number(longitude);
    if (!timezone || items.some((item) =>
      !item.title.trim() || !item.place_query.trim() || !item.start || !item.end
    )) {
      setError("시간대, 장소와 방문 시간을 모두 입력해 주세요.");
      return;
    }
    if ((latitude || longitude) && (
      !latitude || !longitude || !Number.isFinite(parsedLatitude) || !Number.isFinite(parsedLongitude)
    )) {
      setError("위도와 경도는 숫자로 입력해 주세요.");
      return;
    }
    if (items.some((item) => item.start && item.end && item.end <= item.start)) {
      setError("종료 시간은 시작 시간보다 늦어야 합니다.");
      return;
    }
    setError("");
    const fields: ConfirmedDraftFields = {
      timezone,
      items: items.map((item) => ({
        title: item.title.trim(),
        place_query: item.place_query.trim(),
        activity_type: item.activity_type.trim() || "sightseeing",
        start: item.start!,
        end: item.end!,
        fixed: item.fixed,
        rain_sensitive: item.rain_sensitive,
      })),
    };
    if (latitude && longitude) {
      fields.search_origin = { latitude: parsedLatitude, longitude: parsedLongitude };
    }
    await onConfirm(fields);
  }

  return <section className="draft">
    <h2>일정 초안 확인</h2>
    <p>{draft.source_text}</p>
    {draft.questions.map((question) => <p key={question}>확인: {question}</p>)}
    {draft.assumptions.map((assumption) => <p key={assumption}>추정: {assumption}</p>)}
    <form className="draft-fields" onSubmit={submit}>
      <label>시간대<input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Seoul" /></label>
      <p className="field-hint">검색 기준 위치는 선택 사항입니다. 비워두면 첫 장소의 좌표를 사용합니다.</p>
      <div className="coordinate-fields">
        <label>위도<input inputMode="decimal" value={latitude} onChange={(event) => setLatitude(event.target.value)} placeholder="37.5665" /></label>
        <label>경도<input inputMode="decimal" value={longitude} onChange={(event) => setLongitude(event.target.value)} placeholder="126.9780" /></label>
      </div>
      {items.map((item, index) => <fieldset className="draft-item" key={item.id}>
        <legend>일정 {index + 1}</legend>
        <label>표시할 일정 이름<input value={item.title} onChange={(event) => updateItem(index, { title: event.target.value })} /></label>
        <label>Google에서 찾을 장소<input value={item.place_query} onChange={(event) => updateItem(index, { place_query: event.target.value })} /></label>
        <label>활동 종류<input value={item.activity_type} onChange={(event) => updateItem(index, { activity_type: event.target.value })} /></label>
        <div className="time-fields">
          <label>시작 시간<input type="datetime-local" value={item.start?.slice(0, 16) ?? ""} onChange={(event) => updateItem(index, { start: event.target.value })} /></label>
          <label>종료 시간<input type="datetime-local" value={item.end?.slice(0, 16) ?? ""} onChange={(event) => updateItem(index, { end: event.target.value })} /></label>
        </div>
        <div className="check-fields">
          <label><input type="checkbox" checked={item.fixed} onChange={(event) => updateItem(index, { fixed: event.target.checked })} /> 예약·고정 일정</label>
          <label><input type="checkbox" checked={item.rain_sensitive} onChange={(event) => updateItem(index, { rain_sensitive: event.target.checked })} /> 비에 영향받는 일정</label>
        </div>
      </fieldset>)}
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={loading}>{loading ? "장소 확인 중…" : "장소 확인 후 여행 확정"}</button>
    </form>
  </section>;
}
