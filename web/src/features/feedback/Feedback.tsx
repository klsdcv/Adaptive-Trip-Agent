import { useState } from "react";
import type { UserEventInput } from "../../types";

export function Feedback({ onSend }: { onSend: (event: UserEventInput) => void }) {
  const [message, setMessage] = useState("");
  const quickActions: UserEventInput[] = [
    { message: "30분 늦었어요", kind: "delay", payload: { minutes: 30 } },
    { message: "현장 휴무예요", kind: "closed", payload: {} },
    { message: "비가 와요", kind: "weather", payload: {} },
    { message: "걷는 양을 줄여주세요", kind: "fatigue", payload: { level: "high" } },
  ];
  return <section aria-label="상태 입력" className="feedback"><h2>지금 상황을 알려주세요</h2>
    <div className="quick-actions">{quickActions.map((event) => <button type="button" className="secondary" key={event.message} onClick={() => onSend(event)}>{event.message}</button>)}</div>
    <label htmlFor="feedback">직접 입력</label><div className="feedback-input"><input id="feedback" value={message} onChange={(event) => setMessage(event.target.value)} /><button type="button" onClick={() => { if (message.trim()) { onSend({ message, kind: "preference", payload: { preferences: { note: message } } }); setMessage(""); } }}>보내기</button></div>
  </section>;
}
