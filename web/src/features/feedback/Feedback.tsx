import { useState } from "react";

export function Feedback({ onSend }: { onSend: (message: string) => void }) {
  const [message, setMessage] = useState("");
  return <section aria-label="상태 입력" className="feedback"><h2>지금 상황을 알려주세요</h2>
    <div className="quick-actions">{["30분 늦었어요", "현장 휴무예요", "비가 와요", "걷는 양을 줄여주세요"].map((value) => <button type="button" className="secondary" key={value} onClick={() => onSend(value)}>{value}</button>)}</div>
    <label htmlFor="feedback">직접 입력</label><div className="feedback-input"><input id="feedback" value={message} onChange={(event) => setMessage(event.target.value)} /><button type="button" onClick={() => { if (message.trim()) { onSend(message); setMessage(""); } }}>보내기</button></div>
  </section>;
}
