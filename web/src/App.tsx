import { useEffect, useMemo, useState } from "react";

import { tripApi } from "./api";
import { Feedback } from "./features/feedback/Feedback";
import { DraftConfirmation } from "./features/intake/DraftConfirmation";
import { Intake } from "./features/intake/Intake";
import { Timeline } from "./features/itinerary/Timeline";
import { WeatherNotice } from "./features/notifications/WeatherNotice";
import { ProposalList } from "./features/proposals/ProposalList";
import type { ChangeEvent, ConfirmedDraftFields, Draft, Proposal, RunStatus, TripState, UserEventInput } from "./types";

function candidateTitle(index: number, candidate: { items: { title: string }[] }) {
  return candidate.items[0]?.title || `대안 ${index + 1}`;
}

export default function App() {
  const [tripId, setTripId] = useState("");
  const [trip, setTrip] = useState<TripState | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [notification, setNotification] = useState<ChangeEvent | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);

  useEffect(() => {
    if (!tripId) return;
    const timer = window.setInterval(() => {
      Promise.all([tripApi.getProposals(tripId), tripApi.getNotifications(tripId)])
        .then(([proposals, notifications]) => {
          setProposal(proposals[0] ?? null);
          setNotification(notifications.filter((event) => event.kind === "weather").at(-1) ?? null);
        })
        .catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [tripId]);

  useEffect(() => {
    if (!runStatus || (runStatus.status !== "pending" && runStatus.status !== "completed")) return;
    if (runStatus.status === "completed") return;
    const timer = window.setInterval(async () => {
      try {
        const next = await tripApi.getRun(runStatus.run_id);
        setRunStatus(next);
        if (next.status !== "pending") {
          const [loadedTrip, proposals] = await Promise.all([
            tripApi.getTrip(next.trip_id),
            tripApi.getProposals(next.trip_id),
          ]);
          setTrip(loadedTrip);
          setProposal(proposals[0] ?? null);
          setNotice(next.status === "failed" ? "상태는 저장됐지만 재계획에 실패했습니다." : "새 재계획 제안을 준비했습니다.");
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "재계획 상태를 확인하지 못했습니다.");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [runStatus]);

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
      const [loadedTrip, proposals, notifications] = await Promise.all([
        tripApi.getTrip(tripId),
        tripApi.getProposals(tripId),
        tripApi.getNotifications(tripId),
      ]);
      setTrip(loadedTrip);
      setProposal(proposals[0] ?? null);
      setNotification(notifications.filter((event) => event.kind === "weather").at(-1) ?? null);
      setNotice("여행 상태를 불러왔습니다.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "여행을 불러오지 못했습니다."); }
    finally { setLoading(false); }
  }

  async function confirmDraft(fields: ConfirmedDraftFields) {
    if (!draft) return;
    setLoading(true); setError("");
    try {
      const confirmedTrip = await tripApi.confirmDraft(draft.id, fields);
      setTrip(confirmedTrip); setTripId(confirmedTrip.id); setDraft(null);
      setNotice("장소를 확인하고 여행 일정을 확정했습니다.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "여행을 확정하지 못했습니다."); }
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

  async function sendStatus(event: UserEventInput) {
    if (!trip) return;
    setLoading(true); setError("");
    try {
      const run = await tripApi.sendEvent(trip.id, event, trip.version);
      setRunStatus(run);
      setTrip(await tripApi.getTrip(trip.id));
      if (run.status === "completed") setProposal((await tripApi.getProposals(trip.id))[0] ?? null);
      setNotice(run.status === "pending" ? `${event.message} 상태를 반영하고 재계획 중입니다.` : run.status === "failed" ? "상태는 저장됐지만 재계획에 실패했습니다." : `${event.message} 상태를 반영했습니다.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "상태를 반영하지 못했습니다. 최신 상태를 확인해 주세요."); }
    finally { setLoading(false); }
  }

  async function toggleTravelMode() {
    if (!trip) return;
    setLoading(true); setError("");
    try { setTrip(await tripApi.setMode(trip.id, !trip.travel_mode, trip.version)); setNotice(trip.travel_mode ? "여행 모드를 껐습니다." : "여행 모드를 켰습니다."); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "여행 모드를 변경하지 못했습니다."); }
    finally { setLoading(false); }
  }

  return <main><header className="hero"><p className="eyebrow">ADAPTIVE TRIP</p><h1>변화에도 이어지는 여행</h1><p>확정된 일정은 건드리지 않고, 검증된 대안을 먼저 비교합니다.</p></header>
    <section className="load-trip" aria-label="기존 여행 불러오기"><label htmlFor="trip-id">기존 여행 ID</label><input id="trip-id" value={tripId} onChange={(event) => setTripId(event.target.value)} /><button type="button" onClick={loadTrip} disabled={loading}>불러오기</button></section>
    <Intake onSubmit={prepareDraft} loading={loading} />
    {notice && <p className="notice" role="status">{notice}</p>}{error && <p className="error" role="alert">{error}</p>}
    {draft && <DraftConfirmation key={draft.id} draft={draft} loading={loading} onConfirm={confirmDraft} />}
    {trip && notification && <WeatherNotice event={notification} items={trip.items} />}
    {trip && <><section className="trip-controls" aria-label="여행 모드"><p>여행 모드: <strong>{trip.travel_mode ? "켜짐" : "꺼짐"}</strong></p><button type="button" onClick={toggleTravelMode} disabled={loading}>{trip.travel_mode ? "여행 모드 끄기" : "여행 모드 켜기"}</button></section><Timeline items={trip.items} /></>}
    {proposal && <ProposalList proposal={{ id: proposal.id, reason: proposal.reason, candidates: candidateViews }} onAccept={(id) => decide(id, "accept")} onReject={() => decide(null, "reject")} onRefine={() => setNotice("원하는 조건을 상태 입력란에 추가해 주세요.")} />}
    {trip && <Feedback onSend={sendStatus} />}
  </main>;
}
