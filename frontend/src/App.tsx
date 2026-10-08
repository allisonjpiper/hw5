import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_BASE, ApiError } from "./api";
import { money } from "./format";
import { ActivityView, ApprovalsView, CashView } from "./components/OtherViews";
import { ApproveModal, RejectModal, ResetModal, ResolveModal } from "./components/modals";
import { TicketsView, type RunState } from "./components/TicketsView";
import { Toasts, type Toast } from "./components/ui";
import type {
  ActivityResponse,
  ApprovalRequest,
  ApprovalsResponse,
  CashPosition,
  CheckingBalance,
  LiveEvent,
  Ticket,
} from "./types";

type Tab = "tickets" | "approvals" | "cash" | "activity";
type Dialog =
  | { kind: "approve"; req: ApprovalRequest }
  | { kind: "reject"; req: ApprovalRequest }
  | { kind: "resolve"; ticket: Ticket }
  | { kind: "reset" }
  | null;

const NAME_KEY = "cc-desk-name";

// Deep links: #/tickets/101, #/approvals, #/cash, #/activity
function readHash(): { tab: Tab; ticket: number | null } {
  const [, section, id] = window.location.hash.split("/");
  const tab = (["tickets", "approvals", "cash", "activity"] as Tab[]).includes(section as Tab) ? (section as Tab) : "tickets";
  return { tab, ticket: id ? Number(id) || null : null };
}

export default function App() {
  const initial = readHash();
  const [tab, setTab] = useState<Tab>(initial.tab);
  const [online, setOnline] = useState<boolean | null>(null);
  const [today, setToday] = useState("");
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [checking, setChecking] = useState<CheckingBalance | null>(null);
  const [approvals, setApprovals] = useState<ApprovalsResponse | null>(null);
  const [cash, setCash] = useState<CashPosition | null>(null);
  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [feed, setFeed] = useState<LiveEvent[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(initial.ticket);
  const [run, setRun] = useState<RunState | null>(null);
  const [lastEvents, setLastEvents] = useState<Record<number, LiveEvent[]>>({});
  const [name, setName] = useState(() => localStorage.getItem(NAME_KEY) ?? "");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const runRef = useRef<RunState | null>(null);
  runRef.current = run;

  const toast = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 8000 : 5000);
  }, []);

  const saveName = (n: string) => {
    setName(n);
    localStorage.setItem(NAME_KEY, n);
  };

  const refresh = useCallback(async () => {
    try {
      const [t, c, a, cp, act, ev] = await Promise.all([
        api.tickets(),
        api.checking(),
        api.approvals(),
        api.cash(),
        api.activity(15),
        api.events(-1, 60),
      ]);
      setToday(t.today);
      setTickets(t.tickets);
      setChecking(c);
      setApprovals(a);
      setCash(cp);
      setActivity(act);
      setFeed(ev.events);
      setOnline(true);
      setSelectedId((id) => id ?? t.tickets.find((x) => x.open_or_closed === "open")?.id ?? t.tickets[0]?.id ?? null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) setOnline(false);
      else toast("error", (e as Error).message);
    }
  }, [toast]);

  // Keep the URL in sync so a ticket or tab can be bookmarked or shared.
  useEffect(() => {
    const hash = tab === "tickets" && selectedId ? `#/tickets/${selectedId}` : `#/${tab}`;
    if (window.location.hash !== hash) window.history.replaceState(null, "", hash);
  }, [tab, selectedId]);

  // Initial load + gentle background refresh (paused while a run is streaming).
  useEffect(() => {
    refresh();
    const id = setInterval(() => !runRef.current && refresh(), 15000);
    return () => clearInterval(id);
  }, [refresh]);

  // Live feed polling while the agents run.
  useEffect(() => {
    if (!run) return;
    const id = setInterval(async () => {
      const cur = runRef.current;
      if (!cur) return;
      try {
        const res = await api.events(cur.after);
        if (res.events.length) {
          setRun((r) => (r ? { ...r, events: [...r.events, ...res.events], after: res.next_after } : r));
        }
      } catch {
        /* keep polling */
      }
    }, 1200);
    return () => clearInterval(id);
  }, [run?.ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  const startRun = async (ticketId: number, budget: number) => {
    if (budget > 0.5 && !name.trim()) {
      toast("error", "A token budget over $0.50 needs your name. Add it in the top bar first.");
      return;
    }
    let after = -1;
    try {
      after = (await api.events(-1, 1)).next_after;
    } catch {
      /* start from wherever */
    }
    setRun({ ticketId, events: [], after, startedAt: Date.now() });
    try {
      const res = await api.runTicket(ticketId, budget, budget > 0.5 ? name : undefined);
      const tail = await api.events(runRef.current?.after ?? after).catch(() => null);
      const events = [...(runRef.current?.events ?? []), ...(tail?.events ?? [])];
      setLastEvents((m) => ({ ...m, [ticketId]: events }));
      const status = res.decision.ticket_status?.replace("_", " ") ?? "done";
      toast("success", `Ticket #${ticketId}: agents finished (${status}) for $${res.budget.spent_usd.toFixed(4)} in tokens.`);
    } catch (e) {
      toast("error", `Agent run failed: ${(e as Error).message}`);
    } finally {
      setRun(null);
      refresh();
    }
  };

  const pendingCount = approvals?.approval_requests.filter((a) => a.status === "pending").length ?? 0;
  const free = checking?.free_after_obligations ?? null;

  return (
    <>
      <header className="topbar">
        <div className="topbar-row">
          <div className="brand">
            <div className="brand-mark">CC</div>
            <div>
              <h1>Campus Customs · Desk</h1>
              <p>Agent operations dashboard{today && ` · shop date ${today}`}</p>
            </div>
          </div>
          <div className="top-stat" title="cash_accounts.checking">
            <span>Checking</span>
            <b>{money(checking?.balance)}</b>
          </div>
          <div className="top-stat" title="Checking minus open invoices, rent due soon, and queued purchase orders">
            <span>Free after bills</span>
            <b className={free != null && free < 200 ? "warn" : ""}>{money(free)}</b>
          </div>
          <div className="top-actions">
            <input
              className="input"
              style={{ width: 170, background: "rgba(255,255,255,.1)", borderColor: "rgba(255,255,255,.25)", color: "#fff" }}
              placeholder="Your name"
              value={name}
              onChange={(e) => saveName(e.target.value)}
              aria-label="Your name, used for approvals"
            />
            <button className="btn ghost-light" onClick={() => setDialog({ kind: "reset" })} disabled={!!run || !online}>
              ↺ Reset data
            </button>
          </div>
        </div>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <nav className="nav" aria-label="Sections">
            {(
              [
                ["tickets", "Tickets"],
                ["approvals", "Approvals"],
                ["cash", "Cash"],
                ["activity", "Agent activity"],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)} aria-current={tab === key}>
                {label}
                {key === "approvals" && pendingCount > 0 && <span className="count">{pendingCount}</span>}
              </button>
            ))}
          </nav>
          <span className={`status-dot ${online === false ? "off" : run ? "busy" : ""}`} style={{ marginTop: 14 }}>
            {online === false ? "Backend offline" : run ? `Agents working on #${run.ticketId}` : "Connected"}
          </span>
        </div>
      </header>

      <main className="page">
        {online === false && (
          <div className="offline" role="alert">
            <span style={{ fontSize: 20 }}>⚠️</span>
            <div>
              <b>Can't reach the backend at {API_BASE}.</b>
              <div style={{ marginTop: 4 }}>
                Start it from the <code>backend</code> folder with <code>../.venv/bin/uvicorn main:app --reload --port 8000</code>, then{" "}
                <button className="btn sm" onClick={refresh}>
                  try again
                </button>
              </div>
            </div>
          </div>
        )}

        {tab === "tickets" && (
          <TicketsView
            tickets={tickets}
            selectedId={selectedId}
            onSelect={setSelectedId}
            run={run}
            lastEvents={lastEvents}
            runs={activity?.runs ?? []}
            resetAt={activity?.human_actions.find((h) => h.event === "db_reset")?.timestamp ?? null}
            approvals={approvals?.approval_requests ?? []}
            drafts={approvals?.message_drafts ?? []}
            onRun={startRun}
            onResolve={(ticket) => setDialog({ kind: "resolve", ticket })}
            onApprove={(req) => setDialog({ kind: "approve", req })}
            onReject={(req) => setDialog({ kind: "reject", req })}
          />
        )}
        {tab === "approvals" && (
          <ApprovalsView
            approvals={approvals?.approval_requests ?? null}
            checking={checking?.balance ?? null}
            busy={!!run}
            onApprove={(req) => setDialog({ kind: "approve", req })}
            onReject={(req) => setDialog({ kind: "reject", req })}
          />
        )}
        {tab === "cash" && <CashView cash={cash} />}
        {tab === "activity" && (
          <ActivityView runs={activity?.runs ?? null} human={activity?.human_actions ?? []} feed={run ? run.events : feed} />
        )}
      </main>

      {dialog?.kind === "approve" && (
        <ApproveModal
          request={dialog.req}
          checking={checking?.balance ?? null}
          defaultName={name}
          onClose={() => setDialog(null)}
          onSubmit={async (who, reason) => {
            saveName(who);
            const res = await api.approve(dialog.req.id, who, reason);
            if (res.paid) toast("success", `Paid ${money(res.payment?.amount)} to ${res.payment?.payee}. Checking is now ${money(res.checking_balance)}.`);
            else toast("error", `Approved, but the payment was refused: ${res.error}`);
            await refresh();
          }}
        />
      )}
      {dialog?.kind === "reject" && (
        <RejectModal
          request={dialog.req}
          defaultName={name}
          onClose={() => setDialog(null)}
          onSubmit={async (who, reason) => {
            saveName(who);
            await api.reject(dialog.req.id, who, reason);
            toast("info", `Request #${dialog.req.id} rejected. No money moved.`);
            await refresh();
          }}
        />
      )}
      {dialog?.kind === "resolve" && (
        <ResolveModal
          ticket={dialog.ticket}
          defaultName={name}
          onClose={() => setDialog(null)}
          onSubmit={async (who, note) => {
            saveName(who);
            await api.resolveTicket(dialog.ticket.id, who, note);
            toast("success", `Ticket #${dialog.ticket.id} marked resolved.`);
            await refresh();
          }}
        />
      )}
      {dialog?.kind === "reset" && (
        <ResetModal
          onClose={() => setDialog(null)}
          onSubmit={async () => {
            await api.reset();
            setLastEvents({});
            toast("success", "Database reset. All tickets are open and checking is back to the original balance.");
            await refresh();
          }}
        />
      )}
      <Toasts toasts={toasts} dismiss={(id) => setToasts((t) => t.filter((x) => x.id !== id))} />
    </>
  );
}
