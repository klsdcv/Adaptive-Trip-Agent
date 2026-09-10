import type { ChangeEvent, ConfirmedDraftFields, DecisionResult, Draft, Proposal, RunStatus, TripState, UserEventInput } from "./types";

const baseUrl = import.meta.env.VITE_API_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) throw new Error((await response.text()) || "요청을 완료하지 못했습니다.");
  return response.json() as Promise<T>;
}

export const tripApi = {
  createDraft: (text: string) => request<Draft>("/drafts", {
    method: "POST",
    body: JSON.stringify({
      text,
      preferences: { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" },
    }),
  }),
  confirmDraft: (draftId: string, confirmedFields: ConfirmedDraftFields) =>
    request<TripState>(`/drafts/${encodeURIComponent(draftId)}/confirm`, {
      method: "POST",
      body: JSON.stringify({ confirmed_fields: confirmedFields, request_id: crypto.randomUUID() }),
    }),
  getTrip: (tripId: string) => request<TripState>(`/trips/${encodeURIComponent(tripId)}`),
  getProposals: (tripId: string) => request<Proposal[]>(`/trips/${encodeURIComponent(tripId)}/proposals`),
  getNotifications: (tripId: string) => request<ChangeEvent[]>(`/trips/${encodeURIComponent(tripId)}/notifications`),
  decide: (tripId: string, proposalId: string, candidateId: string | null, action: "accept" | "reject") =>
    request<DecisionResult>(`/trips/${encodeURIComponent(tripId)}/decisions`, {
      method: "POST",
      body: JSON.stringify({ proposal_id: proposalId, candidate_id: candidateId, action, request_id: crypto.randomUUID() }),
    }),
  sendEvent: (tripId: string, event: UserEventInput, expectedVersion: number) =>
    request<RunStatus>(`/trips/${encodeURIComponent(tripId)}/events`, {
      method: "POST",
      body: JSON.stringify({
        kind: event.kind,
        payload: event.payload,
        expected_version: expectedVersion,
        request_id: crypto.randomUUID(),
      }),
    }),
  setMode: (tripId: string, enabled: boolean, expectedVersion: number) =>
    request<TripState>(`/trips/${encodeURIComponent(tripId)}/mode`, {
      method: "PATCH",
      body: JSON.stringify({ enabled, expected_version: expectedVersion, request_id: crypto.randomUUID() }),
    }),
};
