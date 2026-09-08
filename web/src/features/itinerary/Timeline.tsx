import type { ItineraryItem } from "../../types";

export function Timeline({ items }: { items: ItineraryItem[] }) {
  return <section aria-label="오늘의 일정" className="timeline">
    <p className="eyebrow">오늘의 일정</p><h2>확정된 일정</h2>
    {items.length === 0 ? <p>아직 확정된 일정이 없습니다.</p> : <ol>{items.map((item) => <li key={item.id}>
      <time dateTime={item.start}>{new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit" }).format(new Date(item.start))}</time>
      <div><strong>{item.title}</strong><span>{item.activity_type}{item.fixed ? " · 고정 조건" : ""}</span></div>
    </li>)}</ol>}
  </section>;
}
