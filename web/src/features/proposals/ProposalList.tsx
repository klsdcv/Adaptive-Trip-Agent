import type { CandidateView, Proposal } from "../../types";

interface ProposalListProps {
  proposal: Pick<Proposal, "id" | "reason"> & { candidates: CandidateView[] };
  onAccept: (candidateId: string) => void;
  onReject: () => void;
  onRefine: () => void;
}

const statusLabel = { pass: "검증됨", fail: "조건 충돌", unknown: "확인 필요" };

export function ProposalList({ proposal, onAccept, onReject, onRefine }: ProposalListProps) {
  return (
    <section aria-label="대안 비교" className="proposal-section">
      <header>
        <p className="eyebrow">변화 알림</p>
        <h2>일정을 이렇게 바꿔볼까요?</h2>
        <p>{proposal.reason}</p>
      </header>
      {proposal.candidates.length === 0 ? (
        <p role="alert">현재 조건을 모두 만족하는 대안이 없습니다. 고정 조건 또는 선호를 조정해 주세요.</p>
      ) : (
        <div className="proposal-grid">
          {proposal.candidates.map((candidate) => (
            <article key={candidate.id} className="proposal-card">
              <h3>{candidate.title}</h3>
              <p>{candidate.rationale}</p>
              <ul aria-label={`${candidate.title} 검증 결과`}>
                {candidate.checks.map((check) => (
                  <li key={`${check.code}-${check.item_id ?? "trip"}`} className={`check check-${check.status}`}>
                    <strong>{statusLabel[check.status]}</strong> {check.message}
                  </li>
                ))}
              </ul>
              <button type="button" onClick={() => onAccept(candidate.id)}>이 대안 선택</button>
            </article>
          ))}
        </div>
      )}
      {proposal.candidates.length > 0 && proposal.candidates.length < 3 && (
        <p role="status">검증을 통과한 대안이 {proposal.candidates.length}개뿐입니다.</p>
      )}
      <div className="proposal-actions">
        <button type="button" className="secondary" onClick={onReject}>기존 일정 유지</button>
        <button type="button" className="secondary" onClick={onRefine}>다른 대안 요청</button>
      </div>
    </section>
  );
}
