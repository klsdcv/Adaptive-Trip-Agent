import { useState } from "react";

interface IntakeProps {
  onSubmit: (text: string) => Promise<void>;
  loading: boolean;
}

export function Intake({ onSubmit, loading }: IntakeProps) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim()) return setError("일정 또는 여행 조건을 입력해 주세요.");
    setError("");
    await onSubmit(text);
  }

  return <form className="intake" onSubmit={submit}>
    <label htmlFor="trip-text">여행 일정 또는 원하는 여행을 알려주세요</label>
    <textarea id="trip-text" value={text} onChange={(event) => setText(event.target.value)} placeholder="예: 내일 15시 야외 정원, 19시 고정 저녁 예약" rows={5} />
    {error && <p role="alert">{error}</p>}
    <button type="submit" disabled={loading}>{loading ? "확인 중…" : "일정 확인 시작"}</button>
  </form>;
}
