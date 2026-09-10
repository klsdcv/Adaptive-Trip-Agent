import { describe, expect, it, vi } from "vitest";

describe("tripApi run status", () => {
  it("loads a run by id", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: "run-1", trip_id: "trip-1", status: "pending", proposal_id: null, error: null }),
    }));
    const { tripApi } = await import("./api");
    await expect(tripApi.getRun("run-1")).resolves.toMatchObject({ run_id: "run-1" });
    expect(fetch).toHaveBeenCalledWith("/api/runs/run-1", expect.any(Object));
  });
});
