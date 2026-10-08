// Thin client for the FastAPI backend. Base URL comes from VITE_API_BASE
// (default http://localhost:8000, the port `uvicorn main:app --reload --port 8000` uses).
import type {
  ActivityResponse,
  ApprovalsResponse,
  ApproveAndPayResponse,
  CashPosition,
  CheckingBalance,
  LiveEventsResponse,
  RunTicketResponse,
  Ticket,
  TicketsResponse,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function readable(detail: unknown): string {
  if (typeof detail === "string") return detail.replace(/^Error calling tool '\w+': /, "");
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (typeof d.stopped === "string") return d.stopped;
    if (Array.isArray(detail)) return detail.map((x) => (x as { msg?: string }).msg ?? String(x)).join("; ");
  }
  return "Something went wrong.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_BASE}.`);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, readable((body as { detail?: unknown }).detail));
  return body as T;
}

const post = <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ agent_run_in_progress: boolean }>("/"),
  tickets: () => request<TicketsResponse>("/tickets"),
  runTicket: (id: number, approveBudget?: number, approvedBy?: string) =>
    post<RunTicketResponse>(`/tickets/${id}/run`, {
      approve_budget: approveBudget ?? 0.5,
      approved_by: approvedBy || null,
    }),
  resolveTicket: (id: number, closedBy: string, note: string) =>
    post<Ticket>(`/tickets/${id}/resolve`, { closed_by: closedBy, note }),
  activity: (runs = 10, ticketId?: number) =>
    request<ActivityResponse>(`/activity?runs=${runs}${ticketId ? `&ticket_id=${ticketId}` : ""}`),
  events: (after: number, limit = 200) => request<LiveEventsResponse>(`/activity/events?after=${after}&limit=${limit}`),
  approvals: () => request<ApprovalsResponse>("/approvals"),
  approve: (id: number, approver: string, reason: string) =>
    post<ApproveAndPayResponse>(`/approvals/${id}/approve`, { approver, reason }),
  reject: (id: number, approver: string, reason: string) =>
    post<Record<string, unknown>>(`/approvals/${id}/reject`, { approver, reason }),
  checking: () => request<CheckingBalance>("/cash/checking"),
  cash: () => request<CashPosition>("/cash"),
  reset: () => post<Record<string, unknown>>("/reset", { confirm: "RESET" }),
};
