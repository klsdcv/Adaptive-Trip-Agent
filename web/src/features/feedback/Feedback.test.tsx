import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Feedback } from "./Feedback";

afterEach(cleanup);

describe("Feedback", () => {
  it("emits a typed delay event from the quick action", () => {
    const send = vi.fn();
    render(<Feedback onSend={send} />);

    fireEvent.click(screen.getByRole("button", { name: "30분 늦었어요" }));

    expect(send).toHaveBeenCalledWith({
      message: "30분 늦었어요",
      kind: "delay",
      payload: { minutes: 30 },
    });
  });
});
