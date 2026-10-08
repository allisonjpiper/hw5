import { useState } from "react";
import { agentInfo, dateTime, TICKET_TYPE_LABEL } from "../format";
import type { ApprovalRequest, BossDecision, LiveEvent, MessageDraft, RunActivity, Ticket } from "../types";
import { ApprovalCard, DraftCard, LiveFeed, RunSummary } from "./pieces";
import { Empty, StatusBadge } from "./ui";

export interface RunState {
  ticketId: number;
  events: LiveEvent[];
  after: number;
  startedAt: number;
}

interface Props {
  tickets: Ticket[] | null;
  selectedId: number | null;
  onSelect: (id: number) => void;
  run: RunState | null;
  lastEvents: Record<number, LiveEvent[]>;
  runs: RunActivity[];
  resetAt: string | null;
  approvals: ApprovalRequest[];
  drafts: MessageDraft[];
  onRun: (id: number, budget: number) => void;
  onResolve: (t: Ticket) => void;
  onApprove: (r: ApprovalRequest) => void;
  onReject: (r: ApprovalRequest) => void;
}

const REQUEST_LINE: Record<string, (t: Ticket) => string> = {
  customer_order: (t) => `${t.qty ?? "?"} × ${t.sku ?? ""} · size ${t.size ?? "?"}`,
  price_override: (t) => `${t.qty ?? "?"} × ${t.sku ?? ""} · size ${t.size ?? "?"}`,
  rent_notice: () => "Rent payment due",
};

export function TicketsView(p: Props) {
  if (!p.tickets) {
    return (
      <div className="tickets-layout">
        <div className="ticket-list">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 110 }} />)}</div>
        <div className="skeleton" style={{ height: 420 }} />
      </div>
    );
  }
  const selected = p.tickets.find((t) => t.id === p.selectedId) ?? null;
  return (
    <div className="tickets-layout">
      <div className="ticket-list" role="list" aria-label="Tickets">
        <p className="section-title" style={{ margin: "0 0 2px" }}>
          {p.tickets.filter((t) => t.open_or_closed === "open").length} open · {p.tickets.filter((t) => t.open_or_closed === "closed").length} closed
        </p>
        {p.tickets.map((t) => (
          <button
            key={t.id}
            role="listitem"
            className={`ticket-card ${t.id === p.selectedId ? "selected" : ""}`}
            onClick={() => p.onSelect(t.id)}
          >
            <div className="tc-top">
              <span>
                <span className="tc-id">#{t.id}</span> <span className="tc-type">· {TICKET_TYPE_LABEL[t.type] ?? t.type}</span>
              </span>
              <StatusBadge status={t.status} />
            </div>
            <div className="tc-title">{t.requester}</div>
            <div className="tc-sub">{t.subject}</div>
            <div className="tc-foot">
              {p.run?.ticketId === t.id ? (
                <span className="running">
                  <span className="spinner" /> Agents working…
                </span>
              ) : (
                <>
                  {t.pending_approval_ids.length > 0 && <span className="chip">💳 {t.pending_approval_ids.length} to approve</span>}
                  {t.draft_ids.length > 0 && <span className="chip">✉️ {t.draft_ids.length} draft</span>}
                  {!t.last_decision && t.status === "open" && <span className="chip">Not started</span>}
                </>
              )}
            </div>
          </button>
        ))}
      </div>

      {selected ? <TicketDetail ticket={selected} {...p} /> : <div className="card"><Empty icon="🎫" title="Pick a ticket to get started" /></div>}
    </div>
  );
}

function TicketDetail({ ticket: t, ...p }: Props & { ticket: Ticket }) {
  const [budget, setBudget] = useState(0.5);
  const running = p.run?.ticketId === t.id;
  const anyRunning = p.run !== null;
  // Runs on this ticket since the last database reset (a reset clears decisions), newest first.
  const ticketRuns = t.last_decision
    ? p.runs.filter(
        (r) => r.tickets.includes(t.id) && r.decisions.some((d) => d.ticket_id === t.id) && (!p.resetAt || r.started > p.resetAt),
      )
    : [];
  const lastRun = ticketRuns[0];
  const earlierRuns = ticketRuns.slice(1);
  const decisionFor = (r: RunActivity): BossDecision | undefined => r.decisions.find((d) => d.ticket_id === t.id);
  const decision = lastRun ? decisionFor(lastRun) : undefined;
  const ticketApprovals = p.approvals.filter((a) => a.ticket_id === t.id);
  const pending = ticketApprovals.filter((a) => a.status === "pending" || a.status === "approved");
  const drafts = p.drafts.filter((d) => d.ticket_id === t.id && d.status !== "superseded");
  const ran = !!t.last_decision;
  const resolved = t.status === "resolved";

  const resolveBlock = resolved
    ? "Already resolved."
    : running
      ? "Wait for the agents to finish."
      : !ran
        ? "Run the agents first."
        : pending.length
          ? `Approve or reject ${pending.length} payment request${pending.length > 1 ? "s" : ""} first.`
          : null;

  const steps = [
    { label: "Agents work the ticket", done: ran, current: !ran },
    { label: "Approve payments", done: ran && pending.length === 0, current: ran && pending.length > 0 },
    { label: "Send drafts", done: resolved || (ran && drafts.length === 0), current: ran && pending.length === 0 && drafts.length > 0 && !resolved },
    { label: "Resolve", done: resolved, current: ran && pending.length === 0 && !resolved },
  ];

  return (
    <div className="stack">
      <div className="card card-pad">
        <div className="detail-head">
          <div>
            <span className="hint">
              Ticket #{t.id} · {TICKET_TYPE_LABEL[t.type] ?? t.type}
            </span>
            <h2>{t.subject}</h2>
            <div className="muted">{t.requester}</div>
          </div>
          <StatusBadge status={t.status} />
        </div>
        {t.notes && <div className="note">“{t.notes}”</div>}
        <div className="detail-meta">
          <div>
            <span>Request</span>
            <b>{(REQUEST_LINE[t.type] ?? (() => "—"))(t)}</b>
          </div>
          <div>
            <span>Received</span>
            <b>{t.created_at ?? "—"}</b>
          </div>
          <div>
            <span>Last decision</span>
            <b>{t.last_decided_at ? dateTime(t.last_decided_at) : "None yet"}</b>
          </div>
        </div>
      </div>

      <div className="card card-pad">
        <div className="steps" aria-label="Progress">
          {steps.map((s, i) => (
            <div key={s.label} className={`step ${s.done ? "done" : s.current ? "current" : ""}`}>
              <span className="dot">{s.done ? "✓" : i + 1}</span>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
        <div className="action-bar" style={{ marginTop: 16 }}>
          <button className="btn primary lg" disabled={anyRunning || resolved} onClick={() => p.onRun(t.id, budget)}>
            {running ? <span className="spinner" /> : "▶"} {running ? "Agents working…" : ran ? "Re-run agent team" : "Run agent team"}
          </button>
          <button className="btn lg" disabled={!!resolveBlock} onClick={() => p.onResolve(t)} title={resolveBlock ?? ""}>
            ✓ Mark resolved
          </button>
          {resolveBlock && !resolved && <span className="why">{resolveBlock}</span>}
          <span className="spacer" />
          <details className="adv">
            <summary>Token budget</summary>
            <div className="row">
              <input
                className="input"
                type="number"
                min={0.05}
                step={0.05}
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
                style={{ width: 100 }}
                aria-label="Token budget in dollars"
              />
              <span className="hint">USD per run. Over $0.50 needs your name.</span>
            </div>
          </details>
        </div>
      </div>

      {(running || p.lastEvents[t.id]?.length) && (
        <div className="card">
          <div className="card-head">
            <h3>{running ? "Live: what the agents are doing" : "Step by step (last run in this session)"}</h3>
            {running && <span className="hint">Usually 20–60 seconds</span>}
          </div>
          <div className="card-pad" style={{ paddingTop: 10 }}>
            {running && (
              <div className="working" style={{ marginBottom: 10 }}>
                <span className="spinner lg" />
                <div>
                  <b>The agent team is working on ticket #{t.id}.</b>
                  <div className="hint" style={{ color: "#234e7d" }}>
                    The Boss reads the ticket, hands work to specialists, and records a decision. Nothing is paid or sent without you.
                  </div>
                </div>
              </div>
            )}
            <LiveFeed events={running ? p.run!.events : p.lastEvents[t.id]} follow={running} />
          </div>
        </div>
      )}

      {pending.length > 0 && (
        <div className="card">
          <div className="card-head">
            <h3>💳 Waiting for your approval</h3>
            <span className="hint">Approving pays from checking right away</span>
          </div>
          <div className="card-pad stack" style={{ gap: 10 }}>
            {pending.map((a) => (
              <ApprovalCard key={a.id} req={a} showTicket={false} disabled={anyRunning} onApprove={() => p.onApprove(a)} onReject={() => p.onReject(a)} />
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-head">
          <h3>🧠 Agent summary</h3>
          {lastRun && <span className="hint">{lastRun.run_id}</span>}
        </div>
        <div className="card-pad">
          {resolved && t.last_decision && (
            <div className="callout ok" style={{ marginTop: 0 }}>
              <b>Resolved.</b> {t.last_decision}
            </div>
          )}
          {lastRun ? (
            <>
              <RunSummary run={lastRun} decision={decision} />
              {earlierRuns.map((r) => (
                <details key={r.run_id} className="adv" style={{ marginTop: 16, borderTop: "1px solid var(--line-2)", paddingTop: 12 }} open={resolved}>
                  <summary>
                    Earlier run · {dateTime(r.started)} · {Object.keys(r.agents).map((a) => agentInfo(a).label).join(", ")}
                  </summary>
                  <RunSummary run={r} decision={decisionFor(r)} />
                </details>
              ))}
            </>
          ) : (
            <Empty icon="🤖" title="No agent run yet for this ticket">
              Click <b>Run agent team</b> and the Boss will route it to the right specialists.
            </Empty>
          )}
        </div>
      </div>

      {drafts.length > 0 && (
        <div className="card">
          <div className="card-head">
            <h3>✉️ Message drafts</h3>
            <span className="hint">Agents never send. Review, copy, and send yourself.</span>
          </div>
          <div className="card-pad stack" style={{ gap: 10 }}>
            {drafts.map((d) => (
              <DraftCard key={d.id} draft={d} />
            ))}
          </div>
        </div>
      )}

      {ticketApprovals.filter((a) => a.status === "paid" || a.status === "rejected").length > 0 && (
        <div className="card">
          <div className="card-head">
            <h3>Payment history</h3>
          </div>
          <div className="card-pad stack" style={{ gap: 10 }}>
            {ticketApprovals
              .filter((a) => a.status === "paid" || a.status === "rejected")
              .map((a) => (
                <ApprovalCard key={a.id} req={a} showTicket={false} onApprove={() => {}} onReject={() => {}} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
