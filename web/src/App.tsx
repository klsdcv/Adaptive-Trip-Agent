import { useEffect, useMemo, useState } from "react";

import { tripApi } from "./api";
import { Feedback } from "./features/feedback/Feedback";
import { Intake } from "./features/intake/Intake";
import { Timeline } from "./features/itinerary/Timeline";
import { ProposalList } from "./features/proposals/ProposalList";
import type { Draft, Proposal, TripState } from "./types";

function candidateTitle(index: number, candidate: { items: { title: string }[] }) {
  return candidate.items[0]?.title || `대안 ${index + 1}`;
}

export default function App() {
  const [tripId, setTripId] = useState("");
  const [trip, setTrip] = useState<TripState | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!tripId) return;
    const timer = window.setInterval(() => {
      tripApi.getProposals(tripId).then((items) => setProposal(items[0] ?? null)).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [tripId]);

  const candidateViews = useMemo(() => proposal?.candidates.map((candidate, index) => ({
    ...candidate,
    title: candidateTitle(index, candidate),
    checks: proposal.reports[candidate.id]?.checks ?? [],
  })) ?? [], [proposal]);

  async function prepareDraft(text: string) {
    setLoading(true); setError("");
    try { setDraft(await tripApi.createDraft(text)); setNotice("초안을 만들었습니다. 질문을 확인한 뒤 여행을 확정해 주세요."); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "초안을 만들지 못했습니다."); }
    finally { setLoading(false); }
  }

  async function loadTrip() {
    if (!tripId.trim()) return;
    setLoading(true); setError("");
    try {
      const [loadedTrip, proposals] = await Promise.all([tripApi.getTrip(tripId), tripApi.getProposals(tripId)]);
      setTrip(loadedTrip); setProposal(proposals[0] ?? null); setNotice("여행 상태를 불러왔습니다.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "여행을 불러오지 못했습니다."); }
    finally { setLoading(false); }
  }

  async function decide(candidateId: string | null, action: "accept" | "reject") {
    if (!proposal || !trip) return;
    setLoading(true); setError("");
    try {
      const result = await tripApi.decide(trip.id, proposal.id, candidateId, action);
      setTrip(result.state); setProposal(null);
      setNotice(result.status === "rejected" ? "기존 확정 일정이 유지됩니다." : "선택한 대안을 일정에 반영했습니다.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "선택을 반영하지 못했습니다. 최신 상태를 확인해 주세요."); }
    finally { setLoading(false); }
  }

  return <main><header className="hero"><p className="eyebrow">ADAPTIVE TRIP</p><h1>변화에도 이어지는 여행</h1><p>확정된 일정은 건드리지 않고, 검증된 대안을 먼저 비교합니다.</p></header>
    <section className="load-trip" aria-label="기존 여행 불러오기"><label htmlFor="trip-id">기존 여행 ID</label><input id="trip-id" value={tripId} onChange={(event) => setTripId(event.target.value)} /><button type="button" onClick={loadTrip} disabled={loading}>불러오기</button></section>
    <Intake onSubmit={prepareDraft} loading={loading} />
    {notice && <p className="notice" role="status">{notice}</p>}{error && <p className="error" role="alert">{error}</p>}
    {draft && <section className="draft"><h2>일정 초안</h2><p>{draft.source_text}</p>{draft.questions.map((question) => <p key={question}>확인: {question}</p>)}</section>}
    {trip && <Timeline items={trip.items} />}
    {proposal && <ProposalList proposal={{ id: proposal.id, reason: proposal.reason, candidates: candidateViews }} onAccept={(id) => decide(id, "accept")} onReject={() => decide(null, "reject")} onRefine={() => setNotice("원하는 조건을 상태 입력란에 추가해 주세요.")} />}
    {trip && <Feedback onSend={(message) => setNotice(`상태 입력을 받았습니다: ${message}`)} />}
  </main>;
}
