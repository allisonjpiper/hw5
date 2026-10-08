import { useEffect, useRef, useState } from "react";
import { agentInfo, cents, dateTime, KIND_LABEL, money, time, TOOL_LABEL } from "../format";
import type { ApprovalRequest, BossDecision, LiveEvent, MessageDraft, RunActivity } from "../types";
import { Avatar, Badge, StatusBadge } from "./ui";

/* ---------------- Live feed ---------------- */

export function LiveFeed({ events, follow = true }: { events: LiveEvent[]; follow?: boolean }) {
  const ref = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (follow && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events, follow]);
  if (!events.length) return <p className="muted" style={{ margin: 0 }}>Waiting for the first step…</p>;
  return (
    <ul className="feed" ref={ref}>
      {events.map((e) => (
        <li key={e.index} className={e.depth ? `indent-${Math.min(e.depth, 2)}` : ""}>
          <span className="t">{time(e.timestamp)}</span>
          <Avatar agent={e.agent} size={24} />
          <span className="txt">
            <b>{agentInfo(e.agent).label}</b> {e.text.replace(new RegExp(`^${agentInfo(e.agent).label}\\s*`), "")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/* ---------------- Tool chips ---------------- */

export function ToolChips({ tools }: { tools: Record<string, number> }) {
  const entries = Object.entries(tools);
  if (!entries.length) return <span className="hint">No tools</span>;
  return (
    <div className="tool-chips">
      {entries.map(([t, n]) => (
        <span key={t} className="tool-chip" title={t}>
          {TOOL_LABEL[t] ?? t} {n > 1 && <b>×{n}</b>}
        </span>
      ))}
    </div>
  );
}

/* ---------------- Agent run summary ---------------- */

const ORDER = ["boss", "inventory", "accounting", "facilities", "customer_service"];

export function RunSummary({ run, decision }: { run: RunActivity; decision: BossDecision | undefined }) {
  const agents = Object.entries(run.agents).sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]));
  const totalCalls = agents.reduce((s, [, a]) => s + a.model_calls, 0);
  return (
    <div className="stack">
      <div className="row" style={{ gap: 18 }}>
        <span className="hint">Run {dateTime(run.started)}</span>
        <span className="hint">{agents.length} agents · {totalCalls} model calls · {cents(run.cost_usd)} in tokens</span>
        {run.refused_delegations > 0 && <Badge kind="pending">{run.refused_delegations} refused hand-off</Badge>}
      </div>

      {decision?.stopped ? (
        <div className="callout danger">The run stopped: {decision.stopped}</div>
      ) : decision ? (
        <div className="decision-box">
          <div className="row" style={{ marginBottom: 8 }}>
            <Avatar agent="boss" />
            <b>Boss's decision</b>
            {decision.ticket_status && <StatusBadge status={decision.ticket_status} />}
          </div>
          <p>{decision.decision}</p>
        </div>
      ) : null}

      <div>
        <p className="section-title">Who did what</p>
        <div className="flow">
          {agents.map(([name, a], i) => (
            <div key={name} style={{ display: "contents" }}>
              {i > 0 && <span className="arrow">→</span>}
              <div className="agent-card">
                <div className="ac-head">
                  <Avatar agent={name} />
                  <b>{agentInfo(name).label}</b>
                  <span className="muted">
                    {a.model_calls} calls · {cents(a.cost_usd)}
                  </span>
                </div>
                {name === "boss" ? (
                  <p>Read the ticket, routed the work{a.delegated_to.length ? ` to ${a.delegated_to.map((d) => agentInfo(d).label).join(" and ")}` : ""}, and recorded the decision above.</p>
                ) : (
                  a.summary && <p>{a.summary.length > 260 ? a.summary.slice(0, 260) + "…" : a.summary}</p>
                )}
                <ToolChips tools={a.tools} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {decision && !decision.stopped && (
        <div className="grid-2">
          <div>
            <p className="section-title">Why</p>
            <ul className="clean">{(decision.reasons ?? []).map((r, i) => <li key={i}>{r}</li>)}</ul>
          </div>
          <div className="stack" style={{ gap: 12 }}>
            {!!decision.human_actions_needed?.length && (
              <div>
                <p className="section-title">What you need to do</p>
                <ul className="checks">{decision.human_actions_needed.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
            {!!decision.risks?.length && (
              <div>
                <p className="section-title">Risks</p>
                <ul className="clean risks">{decision.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
          </div>
        </div>
      )}
      {run.errors.length > 0 && <div className="callout danger">{run.errors.join(" · ")}</div>}
    </div>
  );
}

/* ---------------- Approval card ---------------- */

export function ApprovalCard({
  req,
  onApprove,
  onReject,
  disabled,
  showTicket = true,
}: {
  req: ApprovalRequest;
  onApprove: () => void;
  onReject: () => void;
  disabled?: boolean;
  showTicket?: boolean;
}) {
  return (
    <div className={`approval-card ${req.status}`}>
      <div>
        <div className="row" style={{ gap: 8, marginBottom: 4 }}>
          <Badge kind={req.status}>{req.status[0].toUpperCase() + req.status.slice(1)}</Badge>
          <span className="hint">
            #{req.id} · {KIND_LABEL[req.kind]}
            {showTicket && req.ticket_id ? ` · ticket #${req.ticket_id}` : ""} · requested by {agentInfo(req.requested_by).label}
          </span>
        </div>
        <div className="payee">{req.payee}</div>
        {req.approved_by && (
          <div className="hint">
            {req.status === "rejected" ? "Rejected" : "Approved"} by {req.approved_by} {req.decided_at ? `· ${dateTime(req.decided_at)}` : ""}
          </div>
        )}
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="amount">{money(req.amount)}</div>
        {req.status === "pending" && (
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn danger sm" onClick={onReject} disabled={disabled}>
              Reject
            </button>
            <button className="btn success sm" onClick={onApprove} disabled={disabled}>
              Approve & pay
            </button>
          </div>
        )}
      </div>
      <div className="memo">{req.memo}</div>
    </div>
  );
}

/* ---------------- Draft card ---------------- */

export function DraftCard({ draft }: { draft: MessageDraft }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="draft">
      <div className="row" style={{ marginBottom: 6 }}>
        <Badge kind="draft">Draft · not sent</Badge>
        <span className="hint">
          To {draft.recipient} ({draft.audience}) · by {agentInfo(draft.author_agent).label}
        </span>
        <span className="spacer" />
        <button className="btn sm" onClick={copy}>
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      <div className="subject">{draft.subject}</div>
      <pre>{draft.body}</pre>
    </div>
  );
}
