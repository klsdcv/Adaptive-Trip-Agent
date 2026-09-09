import type { ChangeEvent, ItineraryItem } from "../../types";

interface WeatherNoticeProps {
  event: ChangeEvent;
  items: ItineraryItem[];
}

export function WeatherNotice({ event, items }: WeatherNoticeProps) {
  const probability = event.payload.precipitation_probability;
  const affectedTitles = event.affected_item_ids
    .map((id) => items.find((item) => item.id === id)?.title)
    .filter((title): title is string => Boolean(title));

  return (
    <section className="weather-notice" role="alert">
      <p className="eyebrow">날씨 변화 감지</p>
      <h2>비 예보로 일정 확인이 필요해요</h2>
      <p>
        {typeof probability === "number" && <>강수확률 {probability}% · </>}
        영향 일정: {affectedTitles.length > 0 ? affectedTitles.join(", ") : "확인 중"}
      </p>
    </section>
  );
}
