import { agentInfo, cents, dateTime, KIND_LABEL, money } from "../format";
import type { ApprovalRequest, CashPosition, HumanAction, LiveEvent, RunActivity } from "../types";
import { ApprovalCard, LiveFeed, ToolChips } from "./pieces";
import { Avatar, Badge, Empty } from "./ui";

/* ---------------- Approvals ---------------- */

export function ApprovalsView({
  approvals,
  checking,
  busy,
  onApprove,
  onReject,
}: {
  approvals: ApprovalRequest[] | null;
  checking: number | null;
  busy: boolean;
  onApprove: (r: ApprovalRequest) => void;
  onReject: (r: ApprovalRequest) => void;
}) {
  if (!approvals) return <div className="skeleton" style={{ height: 300 }} />;
  const pending = approvals.filter((a) => a.status === "pending");
  const done = approvals.filter((a) => a.status !== "pending");
  const pendingTotal = pending.reduce((s, a) => s + a.amount, 0);
  return (
    <div className="stack">
      <div className="grid-3">
        <div className="card card-pad">
          <p className="section-title">Waiting for approval</p>
          <div className="big-number" style={{ fontSize: 30 }}>{pending.length}</div>
        </div>
        <div className="card card-pad">
          <p className="section-title">Total requested</p>
          <div className="big-number" style={{ fontSize: 30 }}>{money(pendingTotal)}</div>
        </div>
        <div className="card card-pad">
          <p className="section-title">Checking if all approved</p>
          <div className="big-number" style={{ fontSize: 30, color: checking != null && checking - pendingTotal < 0 ? "var(--red)" : undefined }}>
            {money(checking == null ? null : checking - pendingTotal)}
          </div>
        </div>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>Pending payments & purchase orders</h3>
          <span className="hint">Only a named human can approve. Approving pays immediately.</span>
        </div>
        <div className="card-pad stack" style={{ gap: 10 }}>
          {pending.length ? (
            pending.map((a) => <ApprovalCard key={a.id} req={a} disabled={busy} onApprove={() => onApprove(a)} onReject={() => onReject(a)} />)
          ) : (
            <Empty icon="✅" title="Nothing waiting on you">
              When agents queue a payment, it shows up here.
            </Empty>
          )}
        </div>
      </div>
      {done.length > 0 && (
        <div className="card">
          <div className="card-head">
            <h3>History</h3>
          </div>
          <table className="tbl">
            <thead>
              <tr>
                <th>#</th>
                <th>Type</th>
                <th>Payee</th>
                <th>Ticket</th>
                <th>Status</th>
                <th>Decided by</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {done.map((a) => (
                <tr key={a.id}>
                  <td>{a.id}</td>
                  <td>{KIND_LABEL[a.kind]}</td>
                  <td>{a.payee}</td>
                  <td>{a.ticket_id ? `#${a.ticket_id}` : "—"}</td>
                  <td>
                    <Badge kind={a.status}>{a.status}</Badge>
                  </td>
                  <td>{a.approved_by ?? "—"}</td>
                  <td className="num">{money(a.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------------- Cash ---------------- */

export function CashView({ cash }: { cash: CashPosition | null }) {
  if (!cash) return <div className="skeleton" style={{ height: 300 }} />;
  const checking = cash.cash_accounts.find((a) => a.name === "checking");
  const bal = checking?.balance ?? 0;
  const rent = cash.upcoming_rent_total;
  const inv = cash.open_invoices_total;
  const pos = cash.queued_purchase_orders_total;
  const free = cash.cash_free_after_all_obligations;
  const scale = Math.max(bal, rent + inv + pos, 1);
  const pct = (n: number) => `${Math.max(0, (n / scale) * 100)}%`;
  return (
    <div className="stack">
      <div className="grid-2">
        <div className="card card-pad">
          <p className="section-title">Checking balance</p>
          <div className="big-number">{money(bal)}</div>
          <div className="hint">As of {checking?.date} · no cash comes in, so this only goes down</div>
          <div className="cash-bar" aria-hidden>
            <div style={{ width: pct(rent), background: "#6b46c1" }} />
            <div style={{ width: pct(inv), background: "#b7791f" }} />
            <div style={{ width: pct(pos), background: "#c53030" }} />
            <div style={{ width: pct(Math.max(free, 0)), background: "#2f855a" }} />
          </div>
          <div className="legend">
            <span><i style={{ background: "#6b46c1" }} />Rent due {money(rent)}</span>
            <span><i style={{ background: "#b7791f" }} />Open invoices {money(inv)}</span>
            {pos > 0 && <span><i style={{ background: "#c53030" }} />Queued POs {money(pos)}</span>}
            <span><i style={{ background: "#2f855a" }} />Free {money(free)}</span>
          </div>
        </div>
        <div className="card card-pad">
          <p className="section-title">What's already spoken for</p>
          <div className="kv"><span>Checking</span><b>{money(bal)}</b></div>
          {cash.upcoming_rent.map((l) => (
            <div className="kv" key={l.id}>
              <span>
                Rent · {l.space_name} (due {l.next_due}, {l.days_until_due} days){!l.counted_in_obligations && <span className="hint"> · not yet due</span>}
              </span>
              <span>{l.counted_in_obligations ? `− ${money(l.monthly_rent)}` : money(0)}</span>
            </div>
          ))}
          {cash.open_invoices.map((i) => (
            <div className="kv" key={i.id}>
              <span>Invoice #{i.id} · {i.description} (due {i.due_date})</span>
              <span>− {money(i.amount)}</span>
            </div>
          ))}
          {pos > 0 && <div className="kv"><span>Queued purchase orders</span><span>− {money(pos)}</span></div>}
          <div className="kv total">
            <span>Free after obligations</span>
            <span style={{ color: free < 0 ? "var(--red)" : "var(--green)" }}>{money(free)}</span>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>Payments made</h3>
          <span className="hint">Every row was approved by a human</span>
        </div>
        {cash.payments_log.length ? (
          <table className="tbl">
            <thead>
              <tr>
                <th>#</th>
                <th>What</th>
                <th>Account</th>
                <th>Paid</th>
                <th>Approved by</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {cash.payments_log.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{KIND_LABEL[p.kind] ?? p.kind} #{p.ref_id}</td>
                  <td>{p.account}</td>
                  <td>{dateTime(p.paid_at)}</td>
                  <td>{p.approved_by}</td>
                  <td className="num">− {money(p.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty icon="🧾" title="No payments yet" />
        )}
      </div>
    </div>
  );
}

/* ---------------- Activity ---------------- */

const HUMAN_LABEL: Record<string, string> = {
  human_approval: "Approved",
  payment_executed: "Paid",
  payment_refused: "Payment refused",
  human_rejection: "Rejected",
  human_resolution: "Resolved",
  db_reset: "Reset database",
};

export function ActivityView({ runs, human, feed }: { runs: RunActivity[] | null; human: HumanAction[]; feed: LiveEvent[] }) {
  if (!runs) return <div className="skeleton" style={{ height: 300 }} />;
  const totalCost = runs.reduce((s, r) => s + (r.cost_usd ?? 0), 0);
  return (
    <div className="stack">
      <div className="grid-3">
        <div className="card card-pad">
          <p className="section-title">Recent agent runs</p>
          <div className="big-number" style={{ fontSize: 30 }}>{runs.length}</div>
        </div>
        <div className="card card-pad">
          <p className="section-title">Token spend (these runs)</p>
          <div className="big-number" style={{ fontSize: 30 }}>{cents(totalCost)}</div>
        </div>
        <div className="card card-pad">
          <p className="section-title">Human actions logged</p>
          <div className="big-number" style={{ fontSize: 30 }}>{human.length}</div>
        </div>
      </div>
      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="card">
          <div className="card-head">
            <h3>Agent runs</h3>
            <span className="hint">From output/audit_trail.json</span>
          </div>
          <div className="card-pad stack" style={{ gap: 12 }}>
            {runs.length === 0 && <Empty icon="🤖" title="No runs yet" />}
            {runs.map((r) => (
              <div key={r.run_id} style={{ borderBottom: "1px solid var(--line-2)", paddingBottom: 12 }}>
                <div className="row">
                  <b>Ticket{r.tickets.length > 1 ? "s" : ""} {r.tickets.map((t) => `#${t}`).join(", ")}</b>
                  {r.decisions.map((d) => d.ticket_status && <Badge key={d.ticket_id} kind={d.ticket_status}>{d.ticket_status.replace("_", " ")}</Badge>)}
                  <span className="spacer" />
                  <span className="hint">{dateTime(r.started)} · {cents(r.cost_usd)}</span>
                </div>
                <div className="stack" style={{ gap: 6, marginTop: 8 }}>
                  {Object.entries(r.agents).map(([name, a]) => (
                    <div key={name} className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
                      <Avatar agent={name} size={22} />
                      <div style={{ minWidth: 120, fontSize: 13 }}>
                        <b>{agentInfo(name).label}</b>
                        <div className="hint">{a.model_calls} calls</div>
                      </div>
                      <ToolChips tools={a.tools} />
                    </div>
                  ))}
                </div>
                {r.errors.length > 0 && <div className="callout danger">{r.errors.join(" · ")}</div>}
              </div>
            ))}
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <div className="card-head">
              <h3>Human actions</h3>
            </div>
            <div className="card-pad">
              {human.length ? (
                <ul className="feed">
                  {human.map((h, i) => (
                    <li key={i}>
                      <span className="t">{dateTime(h.timestamp)}</span>
                      <Avatar agent={h.agent} size={22} />
                      <span className="txt">
                        <b>{HUMAN_LABEL[h.event] ?? h.event}</b>
                        {h.ticket_id ? ` · ticket #${h.ticket_id}` : ""}
                        {typeof (h.detail as { approver?: string }).approver === "string" && ` · ${(h.detail as { approver: string }).approver}`}
                        {typeof (h.detail as { closed_by?: string }).closed_by === "string" && ` · ${(h.detail as { closed_by: string }).closed_by}`}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty icon="🧑‍💼" title="No human actions yet" />
              )}
            </div>
          </div>
          <div className="card">
            <div className="card-head">
              <h3>Latest steps</h3>
              <span className="hint">Newest at the bottom</span>
            </div>
            <div className="card-pad">
              <LiveFeed events={feed} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
