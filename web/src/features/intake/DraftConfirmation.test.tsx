import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DraftConfirmation } from "./DraftConfirmation";

describe("DraftConfirmation", () => {
  it("collects local schedule fields before requesting place resolution", async () => {
    const confirm = vi.fn().mockResolvedValue(undefined);

    render(
      <DraftConfirmation
        draft={{
          id: "draft-1",
          source_text: "오사카성 방문",
          items: [],
          questions: ["방문 시간을 알려주세요."],
          assumptions: [],
          confirmed: false,
        }}
        loading={false}
        onConfirm={confirm}
      />,
    );

    fireEvent.change(screen.getByLabelText("위도"), { target: { value: "34.6937" } });
    fireEvent.change(screen.getByLabelText("경도"), { target: { value: "135.5023" } });
    fireEvent.change(screen.getByLabelText("시작 시간"), { target: { value: "2026-09-10T10:00" } });
    fireEvent.change(screen.getByLabelText("종료 시간"), { target: { value: "2026-09-10T12:00" } });
    fireEvent.click(screen.getByRole("button", { name: "장소 확인 후 여행 확정" }));

    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({
      timezone: expect.any(String),
      search_origin: { latitude: 34.6937, longitude: 135.5023 },
      items: [expect.objectContaining({
        title: "오사카성 방문",
        place_query: "오사카성 방문",
        start: "2026-09-10T10:00",
        end: "2026-09-10T12:00",
      })],
    }));
  });
});
