// Shapes returned by the FastAPI backend (backend/main.py, backend/models.py).

export type TicketStatus = "open" | "in_progress" | "awaiting_approval" | "resolved";
export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  notes: string | null;
  sku: string | null;
  size: string | null;
  qty: number | null;
  created_at: string | null;
  status: TicketStatus;
  open_or_closed: "open" | "closed";
  pending_approval_ids: number[];
  draft_ids: number[];
  last_decision: string | null;
  last_decided_at: string | null;
}

export interface TicketsResponse {
  today: string;
  tickets: Ticket[];
}

export interface BossDecision {
  ticket_id: number;
  ticket_type?: string;
  assigned_agents?: AgentName[];
  decision?: string;
  ticket_status?: TicketStatus;
  reasons?: string[];
  approval_request_ids?: number[];
  draft_ids?: number[];
  human_actions_needed?: string[];
  risks?: string[];
  stopped?: string;
}

export interface Budget {
  limit_usd: number;
  approved_by: string | null;
  spent_usd: number;
  input_tokens: number;
  output_tokens: number;
  requests: number;
  by_agent_usd: Record<string, number>;
}

export interface RunTicketResponse {
  run_id: string;
  ticket_id: number;
  decision: BossDecision;
  budget: Budget;
}

export interface AgentActivity {
  summary: string | null;
  model_calls: number;
  tools: Record<string, number>;
  delegated_to: string[];
  cost_usd: number;
}

export interface RunActivity {
  run_id: string;
  started: string;
  ended: string | null;
  tickets: number[];
  agents: Record<string, AgentActivity>;
  tools_used: Record<string, number>;
  refused_delegations: number;
  errors: string[];
  cost_usd: number | null;
  decisions: BossDecision[];
}

export interface HumanAction {
  timestamp: string;
  event: string;
  agent: string;
  ticket_id: number | null;
  detail: Record<string, unknown>;
}

export interface ActivityResponse {
  runs: RunActivity[];
  human_actions: HumanAction[];
  audit_entries_total: number;
}

export interface LiveEvent {
  index: number;
  timestamp: string;
  run_id: string;
  agent: string;
  event: string;
  ticket_id: number | null;
  depth: number;
  text: string;
}

export interface LiveEventsResponse {
  events: LiveEvent[];
  next_after: number;
  run_in_progress: boolean;
}

export interface ApprovalRequest {
  id: number;
  kind: "invoice" | "rent" | "purchase_order";
  ref_id: number | null;
  vendor_id: number | null;
  payee: string;
  amount: number;
  account: string;
  memo: string;
  ticket_id: number | null;
  requested_by: string;
  requested_at: string;
  status: "pending" | "approved" | "rejected" | "paid";
  approved_by: string | null;
  decided_at: string | null;
  payment_id: number | null;
}

export interface MessageDraft {
  id: number;
  ticket_id: number | null;
  audience: "customer" | "vendor" | "landlord";
  recipient: string;
  subject: string;
  body: string;
  author_agent: string;
  created_at: string;
  status: string;
}

export interface ApprovalsResponse {
  approval_requests: ApprovalRequest[];
  message_drafts: MessageDraft[];
}

export interface ApproveAndPayResponse {
  approval: Record<string, unknown>;
  payment: { payment_id: number; amount: number; payee: string; new_balance: number } | null;
  paid: boolean;
  error: string | null;
  checking_balance: number | null;
  ticket_open_approvals: number | null;
}

export interface CheckingBalance {
  account: string;
  balance: number;
  as_of: string;
  open_obligations: number;
  free_after_obligations: number;
}

export interface CashPosition {
  today: string;
  cash_accounts: { name: string; balance: number; date: string }[];
  total_cash: number;
  open_invoices: { id: number; vendor_id: number; amount: number; due_date: string; status: string; description: string }[];
  open_invoices_total: number;
  upcoming_rent: {
    id: number;
    space_name: string;
    landlord: string;
    monthly_rent: number;
    next_due: string;
    days_until_due: number;
    counted_in_obligations: boolean;
  }[];
  upcoming_rent_total: number;
  payments_log: { id: number; kind: string; ref_id: number; amount: number; account: string; paid_at: string; approved_by: string }[];
  approval_queue: { id: number; kind: string; ref_id: number | null; payee: string; amount: number; status: string }[];
  queued_purchase_orders_total: number;
  cash_free_after_all_obligations: number;
}
