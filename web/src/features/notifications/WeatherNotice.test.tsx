import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";

import { WeatherNotice } from "./WeatherNotice";
import type { ChangeEvent, ItineraryItem } from "../../types";

const event: ChangeEvent = {
  id: "rain-alert",
  trip_id: "trip-rain",
  kind: "weather",
  at: "2026-09-08T14:30:00+09:00",
  affected_item_ids: ["park"],
  payload: {
    precipitation_probability: 80,
    forecast_at: "2026-09-08T15:00:00+09:00",
  },
  fingerprint: "trip-rain:park:rain:2026-09-08T15:00:00+09:00",
};

const items = [{ id: "park", title: "오사카성 공원" }] as ItineraryItem[];

describe("WeatherNotice", () => {
  it("shows the rain probability and affected itinerary item", () => {
    render(<WeatherNotice event={event} items={items} />);

    expect(screen.getByRole("alert")).toHaveTextContent("강수확률 80%");
    expect(screen.getByRole("alert")).toHaveTextContent("오사카성 공원");
  });
});
