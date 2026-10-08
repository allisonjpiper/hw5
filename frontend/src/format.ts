import type { AgentName, TicketStatus } from "./types";

export const money = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD" });

export const cents = (n: number | null | undefined) => (n == null ? "—" : `$${n.toFixed(4)}`);

export const time = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }) : "";

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";

export const TICKET_TYPE_LABEL: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Price override",
};

export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  awaiting_approval: "Awaiting approval",
  resolved: "Resolved",
};

export const AGENTS: Record<AgentName | "human" | "dashboard" | "desk", { label: string; color: string; initials: string }> = {
  boss: { label: "Boss", color: "#0f2d52", initials: "B" },
  inventory: { label: "Inventory", color: "#2f855a", initials: "I" },
  accounting: { label: "Accounting", color: "#b7791f", initials: "A" },
  facilities: { label: "Facilities", color: "#6b46c1", initials: "F" },
  customer_service: { label: "Customer Service", color: "#c53030", initials: "CS" },
  human: { label: "You", color: "#2b6cb0", initials: "👤" },
  dashboard: { label: "Dashboard", color: "#4a5568", initials: "D" },
  desk: { label: "Desk", color: "#718096", initials: "•" },
};

export const agentInfo = (name: string) =>
  AGENTS[name as keyof typeof AGENTS] ?? { label: name, color: "#718096", initials: name.slice(0, 1).toUpperCase() };

export const TOOL_LABEL: Record<string, string> = {
  check_order_fulfillment: "Order fact sheet",
  check_rent_coverage: "Rent fact sheet",
  price_bulk_order: "Bulk-order fact sheet",
  list_ticket_queue: "Ticket queue",
  lookup_inventory_pricing: "Inventory & pricing",
  list_vendors_invoices: "Vendors & invoices",
  get_cash_position: "Cash position",
  request_payment_approval: "Request approval",
  pay_approved_request: "Pay",
  save_message_draft: "Save draft",
  list_approval_queue: "Approval queue",
  record_ticket_decision: "Record decision",
  delegate: "Hand off work",
};

export const KIND_LABEL: Record<string, string> = {
  invoice: "Vendor invoice",
  rent: "Rent",
  purchase_order: "Purchase order",
};
