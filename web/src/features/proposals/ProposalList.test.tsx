import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ProposalList } from "./ProposalList";
import type { CandidateView, Proposal } from "../../types";

const threeChoiceProposal = {
  id: "proposal-rain",
  reason: "Rain affects the outdoor visit.",
  candidates: [
    { id: "option-museum", title: "Museum visit", rationale: "Move indoors.", items: [], signature: "museum", checks: [] },
    { id: "option-cafe", title: "Cafe break", rationale: "Wait out the rain.", items: [], signature: "cafe", checks: [] },
    { id: "option-market", title: "Covered market", rationale: "Keep walking short.", items: [], signature: "market", checks: [] },
  ],
} satisfies Pick<Proposal, "id" | "reason"> & { candidates: CandidateView[] };

describe("ProposalList", () => {
  it("shows three alternatives without changing the itinerary before selection", () => {
    const accept = vi.fn();

    render(
      <ProposalList
        proposal={threeChoiceProposal}
        onAccept={accept}
        onReject={vi.fn()}
        onRefine={vi.fn()}
      />,
    );

    expect(screen.getAllByRole("button", { name: "이 대안 선택" })).toHaveLength(3);
    expect(accept).not.toHaveBeenCalled();
  });
});
