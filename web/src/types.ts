export type CheckStatus = "pass" | "fail" | "unknown";

export interface Money {
  amount: string;
  currency: string;
  certainty: "confirmed" | "estimated";
}

export interface ItineraryItem {
  id: string;
  place_id: string;
  title: string;
  activity_type: string;
  start: string;
  end: string;
  status: "pending" | "active" | "completed";
  fixed: boolean;
  cost: Money | null;
  rain_sensitive: boolean;
}

export interface Check {
  code: string;
  status: CheckStatus;
  item_id: string | null;
  evidence_ids: string[];
  message: string;
}

export interface Candidate {
  id: string;
  items: ItineraryItem[];
  rationale: string;
  signature: string;
}

export interface CandidateView extends Candidate {
  title: string;
  checks: Check[];
}

export interface Proposal {
  id: string;
  trip_id: string;
  base_version: number;
  created_at: string;
  expires_at: string;
  candidates: Candidate[];
  reports: Record<string, { checks: Check[] }>;
  status: "pending" | "accepted" | "rejected" | "stale";
  reason: string;
}

export interface TripState {
  id: string;
  version: number;
  timezone: string;
  items: ItineraryItem[];
  travel_mode: boolean;
}

export interface Draft {
  id: string;
  source_text: string;
  items: ItineraryItem[];
  questions: string[];
  assumptions: string[];
  confirmed: boolean;
}

export interface DecisionResult {
  status: "applied" | "rejected" | "stale" | "needs_confirmation" | "invalid";
  state: TripState;
  proposal_id: string;
}
