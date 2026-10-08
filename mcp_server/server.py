"""Campus Customs MCP server.

The only way the agents reach data/campus_customs_new.db. Every shop fact an
agent uses comes from one of these tools, and every database write goes
through one of them, with the safety rules from output/harness.md enforced
here instead of trusted to the model.

Ticket fact sheets (read-only, one per open ticket):
  check_order_fulfillment (101), check_rent_coverage (102), price_bulk_order (103)
Read-only lookups:
  list_ticket_queue, lookup_inventory_pricing, list_vendors_invoices,
  get_cash_position, list_approval_queue
Agent writes (validated here):
  request_payment_approval, pay_approved_request, save_message_draft,
  record_ticket_decision
Human-only actions for the dashboard backend (in no agent's allowlist):
  human_decide_approval, human_reset_database, human_resolve_ticket
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from fastmcp import FastMCP

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"
DB_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_DB", DEFAULT_DB))
SEED_DB = Path(os.environ.get("CAMPUS_CUSTOMS_SEED", DEFAULT_DB.parent / "campus_customs.db"))  # the original, untouched
BACKUP_DIR = DB_PATH.parent / "backups"
SHOP_TABLES = ("desk", "inventory", "pricing", "vendors", "leases", "cash_accounts", "payments", "invoices", "tickets")
AGENT_TABLES = ("approval_requests", "message_drafts", "ticket_decisions")

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
TICKET_STATUSES = {"open", "in_progress", "awaiting_approval", "resolved"}
EXECUTORS = AGENT_NAMES | {"dashboard"}  # who may trigger pay_approved_request (dashboard = human-approved via the backend)

mcp = FastMCP("campus-customs")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open, commit on success / roll back on error, and always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_agent_tables(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_agent_tables(conn: sqlite3.Connection) -> None:
    """Tables the agents write to. The original 9 shop tables are left as-is.

    Checked on every connection so they come back after a database reset.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS approval_requests (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,               -- invoice | rent | purchase_order
            ref_id INTEGER,                   -- invoices.id or leases.id (NULL for a new PO)
            vendor_id INTEGER,                -- payee for invoices / POs
            payee TEXT NOT NULL,
            amount REAL NOT NULL,
            account TEXT NOT NULL,
            memo TEXT NOT NULL,
            ticket_id INTEGER,
            requested_by TEXT NOT NULL,       -- agent name
            requested_at TEXT NOT NULL,
            status TEXT NOT NULL,             -- pending | approved | rejected | paid
            approved_by TEXT,                 -- set by a human only (Problem 6)
            decided_at TEXT,
            payment_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS message_drafts (
            id INTEGER PRIMARY KEY,
            ticket_id INTEGER,
            audience TEXT NOT NULL,           -- customer | vendor | landlord
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            author_agent TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL              -- draft_not_sent | superseded (never 'sent')
        );
        CREATE TABLE IF NOT EXISTS ticket_decisions (
            id INTEGER PRIMARY KEY,
            ticket_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            decision TEXT NOT NULL,
            decided_by TEXT NOT NULL,
            decided_at TEXT NOT NULL
        );
        """
    )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _check_agent(name: str) -> str:
    name = name.strip().lower()
    if name not in AGENT_NAMES:
        raise ValueError(f"Unknown agent '{name}'. Expected one of {sorted(AGENT_NAMES)}.")
    return name


def _add_month(iso_day: str) -> str:
    d = date.fromisoformat(iso_day)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not add a month to {iso_day}")


def _committed_pending(conn: sqlite3.Connection) -> float:
    """Money already queued for approval (pending or approved, not yet paid)."""
    return conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM approval_requests WHERE status IN ('pending', 'approved')"
    ).fetchone()[0]


def _today(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _get_ticket(conn: sqlite3.Connection, ticket_id: int, expected_type: str) -> dict:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise ValueError(f"Ticket {ticket_id} not found in the database.")
    if row["type"] != expected_type:
        raise ValueError(
            f"Ticket {ticket_id} is type '{row['type']}', but this tool handles '{expected_type}' tickets."
        )
    return dict(row)


@mcp.tool
def check_order_fulfillment(ticket_id: int) -> dict:
    """Ticket 101 (customer_order): can this customer order be filled?

    Looks up the ticket's sku/size/qty, the stock on hand for that size, and
    the linked restock invoice (status, due date, vendor, vendor lead days).
    Use this before promising a customer an item or a delivery date.
    """
    with _connect() as conn:
        ticket = _get_ticket(conn, ticket_id, "customer_order")
        today = _today(conn)

        stock = conn.execute(
            "SELECT name, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (ticket["sku"], ticket["size"]),
        ).fetchone()
        price = conn.execute(
            "SELECT list_price FROM pricing WHERE sku = ?", (ticket["sku"],)
        ).fetchone()

        on_hand = stock["qty"] if stock else 0
        result = {
            "ticket_id": ticket_id,
            "requester": ticket["requester"],
            "sku": ticket["sku"],
            "size": ticket["size"],
            "qty_requested": ticket["qty"],
            "product_name": stock["name"] if stock else None,
            "qty_on_hand": on_hand,
            "location": stock["location"] if stock else None,
            "list_price": price["list_price"] if price else None,
            "can_fill_now": on_hand >= (ticket["qty"] or 0),
            "today": today,
            "restock_invoice": None,
        }

        if ticket["invoice_id"] is not None:
            inv = conn.execute(
                """SELECT i.id, i.amount, i.due_date, i.status, i.description,
                          v.name AS vendor_name, v.lead_days
                   FROM invoices i JOIN vendors v ON v.id = i.vendor_id
                   WHERE i.id = ?""",
                (ticket["invoice_id"],),
            ).fetchone()
            if inv:
                inv = dict(inv)
                inv["days_overdue"] = max(0, _days_between(inv["due_date"], today))
                result["restock_invoice"] = inv

        return result


@mcp.tool
def check_rent_coverage(ticket_id: int) -> dict:
    """Ticket 102 (rent_notice): can the shop afford the rent that is due?

    Looks up the linked lease (landlord, rent, due date), days until due,
    the cash account balances, all open vendor invoices, and what the
    checking balance would be after paying rent alone and rent plus all
    open invoices. Read-only: it does not record a payment.
    """
    with _connect() as conn:
        ticket = _get_ticket(conn, ticket_id, "rent_notice")
        today = _today(conn)

        lease = conn.execute(
            "SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)
        ).fetchone()
        if lease is None:
            raise ValueError(f"Ticket {ticket_id} has no matching lease in the database.")

        accounts = [dict(r) for r in conn.execute("SELECT * FROM cash_accounts")]
        open_invoices = [
            dict(r)
            for r in conn.execute(
                """SELECT i.id, i.amount, i.due_date, i.description, v.name AS vendor_name
                   FROM invoices i JOIN vendors v ON v.id = i.vendor_id
                   WHERE i.status = 'open'"""
            )
        ]
        already_paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS paid FROM payments WHERE kind = 'rent' AND ref_id = ?",
            (lease["id"],),
        ).fetchone()["paid"]

        total_cash = sum(a["balance"] for a in accounts)
        rent = lease["monthly_rent"]
        open_total = sum(i["amount"] for i in open_invoices)

        return {
            "ticket_id": ticket_id,
            "requester": ticket["requester"],
            "lease_id": lease["id"],
            "space_name": lease["space_name"],
            "landlord": lease["landlord"],
            "monthly_rent": rent,
            "next_due": lease["next_due"],
            "today": today,
            "days_until_due": _days_between(today, lease["next_due"]),
            "rent_already_paid_in_payments_log": already_paid,
            "cash_accounts": accounts,
            "total_cash": total_cash,
            "open_invoices": open_invoices,
            "open_invoices_total": open_total,
            "cash_after_rent": total_cash - rent,
            "cash_after_rent_and_open_invoices": total_cash - rent - open_total,
            "can_cover_rent": total_cash >= rent,
        }


@mcp.tool
def price_bulk_order(ticket_id: int) -> dict:
    """Ticket 103 (price_override): how much of a bulk order can be filled, and at what price floor?

    Looks up the ticket's sku/size/qty, stock on hand for that size, the
    shortfall, unit cost, list price, per-unit margin, and the lowest
    per-unit price that does not sell below cost. Also lists vendors with
    their specialty and lead days in case the shortfall needs a reprint.
    """
    with _connect() as conn:
        ticket = _get_ticket(conn, ticket_id, "price_override")

        stock = conn.execute(
            "SELECT name, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (ticket["sku"], ticket["size"]),
        ).fetchone()
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (ticket["sku"],)
        ).fetchone()
        if price is None:
            raise ValueError(f"No pricing found for {ticket['sku']}.")
        all_sizes = [
            dict(r)
            for r in conn.execute(
                "SELECT size, qty FROM inventory WHERE sku = ?", (ticket["sku"],)
            )
        ]
        vendors = [dict(r) for r in conn.execute("SELECT name, specialty, lead_days FROM vendors")]

        requested = ticket["qty"] or 0
        on_hand = stock["qty"] if stock else 0
        unit_cost, list_price = price["unit_cost"], price["list_price"]

        return {
            "ticket_id": ticket_id,
            "requester": ticket["requester"],
            "request_notes": ticket["notes"],
            "sku": ticket["sku"],
            "size": ticket["size"],
            "product_name": stock["name"] if stock else None,
            "qty_requested": requested,
            "qty_on_hand": on_hand,
            "qty_fillable_now": min(on_hand, requested),
            "shortfall": max(0, requested - on_hand),
            "stock_by_size": all_sizes,
            "unit_cost": unit_cost,
            "list_price": list_price,
            "margin_per_unit": list_price - unit_cost,
            "max_discount_pct_before_loss": round((list_price - unit_cost) / list_price * 100, 1),
            "price_floor_per_unit": unit_cost,
            "full_order_at_list_price": requested * list_price,
            "full_order_cost": requested * unit_cost,
            "vendors": vendors,
        }


# ---------------------------------------------------------------------------
# Read-only lookups used across agents
# ---------------------------------------------------------------------------


@mcp.tool
def list_ticket_queue(include_resolved: bool = False) -> dict:
    """Ticket queue: list the shop's tickets for the Boss to read and route.

    Returns today's desk date and every ticket (id, type, requester, subject,
    sku/size/qty, linked lease_id / invoice_id, status, notes, created_at),
    plus any decisions already recorded for each ticket. By default only
    tickets that are not 'resolved' are returned.
    """
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM tickets ORDER BY id")]
        if not include_resolved:
            rows = [r for r in rows if r["status"] != "resolved"]
        for r in rows:
            r["decision_history"] = [
                dict(d)
                for d in conn.execute(
                    "SELECT status, decision, decided_by, decided_at FROM ticket_decisions WHERE ticket_id = ? ORDER BY id",
                    (r["id"],),
                )
            ]
        return {"today": _today(conn), "tickets": rows}


@mcp.tool
def lookup_inventory_pricing(sku: str | None = None) -> dict:
    """Inventory and pricing: stock on hand per size, with unit cost, list price and margin.

    Pass a sku (e.g. 'CC-HOOD-NAVY') for one product, or leave it empty for
    the whole catalogue. Each row shows sku, name, size, qty, location,
    unit_cost, list_price and margin_per_unit; out_of_stock lists rows at 0.
    """
    with _connect() as conn:
        query = """SELECT i.sku, i.name, i.size, i.qty, i.location,
                          p.unit_cost, p.list_price, p.list_price - p.unit_cost AS margin_per_unit
                   FROM inventory i LEFT JOIN pricing p ON p.sku = i.sku"""
        params: tuple = ()
        if sku:
            query += " WHERE i.sku = ?"
            params = (sku,)
        rows = [dict(r) for r in conn.execute(query + " ORDER BY i.sku, i.size", params)]
        if sku and not rows:
            raise ValueError(f"No inventory found for sku '{sku}'.")
        return {
            "items": rows,
            "out_of_stock": [f"{r['sku']} {r['size']}" for r in rows if r["qty"] == 0],
        }


@mcp.tool
def list_vendors_invoices() -> dict:
    """Vendors and their invoices: who supplies what, lead times, and what the shop owes them.

    Returns each vendor (id, name, specialty, lead_days) with its invoices
    (id, amount, due_date, status, description, days_overdue as of the desk
    date) and any payments already logged against those invoices.
    """
    with _connect() as conn:
        today = _today(conn)
        vendors = [dict(v) for v in conn.execute("SELECT * FROM vendors ORDER BY id")]
        for v in vendors:
            invoices = [
                dict(i)
                for i in conn.execute("SELECT * FROM invoices WHERE vendor_id = ? ORDER BY id", (v["id"],))
            ]
            for i in invoices:
                i["days_overdue"] = max(0, _days_between(i["due_date"], today)) if i["status"] == "open" else 0
                i["payments"] = [
                    dict(p)
                    for p in conn.execute(
                        "SELECT id, amount, account, paid_at, approved_by FROM payments WHERE kind = 'invoice' AND ref_id = ?",
                        (i["id"],),
                    )
                ]
            v["invoices"] = invoices
        return {"today": today, "vendors": vendors}


@mcp.tool
def get_cash_position(rent_window_days: int = 30) -> dict:
    """Cash position: balances, every known obligation, and what is truly free to spend.

    Returns cash_accounts, open invoices, the next rent due on each lease,
    the payments log, the approval queue total (pending/approved but not yet
    paid), and cash_free_after_all_obligations = cash - open invoices - rent
    due within rent_window_days of the desk date - queued POs. Rent further
    out (e.g. next month's, after this month's is paid) is listed but not
    subtracted, but `warnings` flags any later rent that free cash can't cover.
    No cash ever comes in, so this is the ceiling on spending.
    """
    with _connect() as conn:
        today = _today(conn)
        accounts = [dict(a) for a in conn.execute("SELECT * FROM cash_accounts")]
        open_invoices = [dict(i) for i in conn.execute("SELECT * FROM invoices WHERE status = 'open'")]
        leases = [dict(l) for l in conn.execute("SELECT id, space_name, landlord, monthly_rent, next_due FROM leases")]
        for l in leases:
            l["days_until_due"] = _days_between(today, l["next_due"])
            l["counted_in_obligations"] = l["days_until_due"] <= rent_window_days
        payments = [dict(p) for p in conn.execute("SELECT * FROM payments ORDER BY id")]
        queued = [
            dict(a)
            for a in conn.execute(
                "SELECT id, kind, ref_id, payee, amount, status FROM approval_requests WHERE status IN ('pending', 'approved')"
            )
        ]
        total_cash = sum(a["balance"] for a in accounts)
        invoices_total = sum(i["amount"] for i in open_invoices)
        rent_total = sum(l["monthly_rent"] for l in leases if l["counted_in_obligations"])
        # Queued invoice/rent requests are already counted above; only new POs add on top.
        extra_pos = sum(q["amount"] for q in queued if q["kind"] == "purchase_order")
        free = total_cash - invoices_total - rent_total - extra_pos
        later_rent = [l for l in leases if not l["counted_in_obligations"]]
        warnings = [
            f"Rent of {l['monthly_rent']:.2f} for {l['space_name']} is due {l['next_due']} "
            f"({l['days_until_due']} days), outside the {rent_window_days}-day window, and free cash "
            f"({free:.2f}) cannot cover it with no incoming cash."
            for l in later_rent
            if l["monthly_rent"] > free
        ]
        return {
            "today": today,
            "cash_accounts": accounts,
            "total_cash": total_cash,
            "open_invoices": open_invoices,
            "open_invoices_total": invoices_total,
            "upcoming_rent": leases,
            "upcoming_rent_total": rent_total,
            "rent_window_days": rent_window_days,
            "payments_log": payments,
            "approval_queue": queued,
            "queued_purchase_orders_total": extra_pos,
            "cash_free_after_all_obligations": free,
            "warnings": warnings,
            "cash_inflows": "none — the shop has no incoming cash; balances only go down",
        }


# ---------------------------------------------------------------------------
# Money: approval requests and the pay tool (Accounting only)
# ---------------------------------------------------------------------------


@mcp.tool
def request_payment_approval(
    kind: str,
    amount: float,
    memo: str,
    requested_by: str,
    ticket_id: int | None = None,
    ref_id: int | None = None,
    vendor_id: int | None = None,
    account: str = "checking",
) -> dict:
    """Request human approval for a payment or purchase order. Does NOT move money.

    kind: 'invoice' (ref_id = invoices.id), 'rent' (ref_id = leases.id), or
    'purchase_order' (vendor_id required; memo must say sku/size/qty/unit cost).
    Validates against the database: invoice must be open and the amount must
    equal the invoice amount; rent must equal monthly_rent; amount must be
    positive and not exceed the account balance; no duplicate pending request
    for the same invoice/lease. Creates a 'pending' row in approval_requests
    for a human to approve or reject.
    """
    requested_by = _check_agent(requested_by)
    if amount <= 0:
        raise ValueError("Amount must be positive. The shop has no incoming cash, so there are no refunds or deposits.")
    if not memo.strip():
        raise ValueError("A memo explaining the payment is required.")
    with _connect() as conn:
        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            raise ValueError(f"No cash account named '{account}'.")

        if kind == "invoice":
            inv = conn.execute(
                "SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (ref_id,),
            ).fetchone()
            if inv is None:
                raise ValueError(f"Invoice {ref_id} not found.")
            if inv["status"] != "open":
                raise ValueError(f"Invoice {ref_id} is '{inv['status']}', not open. It must not be paid twice.")
            if abs(inv["amount"] - amount) > 0.005:
                raise ValueError(f"Amount {amount} does not match invoice {ref_id} amount {inv['amount']}.")
            payee, vendor_id = inv["vendor_name"], inv["vendor_id"]
        elif kind == "rent":
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                raise ValueError(f"Lease {ref_id} not found.")
            if abs(lease["monthly_rent"] - amount) > 0.005:
                raise ValueError(f"Amount {amount} does not match lease {ref_id} rent {lease['monthly_rent']}.")
            payee, vendor_id = lease["landlord"], None
        elif kind == "purchase_order":
            vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
            if vendor is None:
                raise ValueError(f"Vendor {vendor_id} not found. Purchase orders need a vendor_id from the vendors table.")
            payee, ref_id = vendor["name"], None
        else:
            raise ValueError("kind must be 'invoice', 'rent', or 'purchase_order'.")

        if kind in ("invoice", "rent"):
            dup = conn.execute(
                "SELECT id FROM approval_requests WHERE kind = ? AND ref_id = ? AND status IN ('pending', 'approved')",
                (kind, ref_id),
            ).fetchone()
            if dup:
                raise ValueError(f"Approval request {dup['id']} already covers this {kind}. Do not queue it twice.")

        queued_before = _committed_pending(conn)
        if amount > acct["balance"] - queued_before:
            raise ValueError(
                f"Amount {amount} exceeds the {account} balance {acct['balance']} minus {queued_before} already "
                "queued for approval. The shop does not go into debt."
            )

        cur = conn.execute(
            """INSERT INTO approval_requests
               (kind, ref_id, vendor_id, payee, amount, account, memo, ticket_id, requested_by, requested_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (kind, ref_id, vendor_id, payee, amount, account, memo, ticket_id, requested_by, _now()),
        )
        return {
            "approval_request_id": cur.lastrowid,
            "status": "pending",
            "kind": kind,
            "payee": payee,
            "amount": amount,
            "account": account,
            "balance_now": acct["balance"],
            "queued_before_this_request": queued_before,
            "balance_if_all_queued_paid": acct["balance"] - queued_before - amount,
            "note": "No money has moved. A human must approve this request before the pay tool will act.",
        }


@mcp.tool
def pay_approved_request(approval_request_id: int, requested_by: str) -> dict:
    """Pay tool: execute ONE human-approved payment and update every affected table.

    Refuses unless the approval request has status 'approved' with a human
    name in approved_by (agents cannot approve). Refuses if the account has
    no remaining cash or the payment would make the balance negative. On
    success, in one transaction: inserts a payments row, subtracts the
    amount from cash_accounts, marks the invoice 'paid' (invoice kind) or
    moves the lease's next_due forward one month (rent kind), and marks the
    approval request 'paid'. requested_by is the agent (or 'dashboard' when
    the human approved it from the backend) triggering the payment.
    """
    requested_by = requested_by.strip().lower()
    if requested_by not in EXECUTORS:
        raise ValueError(f"Unknown executor '{requested_by}'. Expected one of {sorted(EXECUTORS)}.")
    with _connect() as conn:
        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_request_id,)).fetchone()
        if req is None:
            raise ValueError(f"Approval request {approval_request_id} not found.")
        if req["status"] == "paid":
            raise ValueError(f"Approval request {approval_request_id} is already paid (payment {req['payment_id']}).")
        if req["status"] != "approved" or not (req["approved_by"] or "").strip():
            raise ValueError(
                f"Approval request {approval_request_id} is '{req['status']}'. A human must approve it before payment."
            )
        if (req["approved_by"] or "").strip().lower() in AGENT_NAMES:
            raise ValueError("approved_by is an agent name. Only a human can approve a payment.")

        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (req["account"],)).fetchone()
        if acct is None:
            raise ValueError(f"No cash account named '{req['account']}'.")
        if acct["balance"] <= 0:
            raise ValueError(f"The {req['account']} account has no remaining cash. Payment refused.")
        if req["amount"] > acct["balance"]:
            raise ValueError(
                f"Payment of {req['amount']} would overdraw {req['account']} (balance {acct['balance']}). Refused: no debt."
            )

        if req["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                raise ValueError(f"Invoice {req['ref_id']} is not open. Refusing to pay it twice.")

        paid_at = _now()
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (req["kind"], req["ref_id"] if req["kind"] != "purchase_order" else req["id"], req["amount"],
             req["account"], paid_at, req["approved_by"]),
        )
        payment_id = cur.lastrowid
        conn.execute(
            "UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
            (req["amount"], _today(conn), req["account"]),
        )
        tables_updated = ["payments", "cash_accounts", "approval_requests"]
        if req["kind"] == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
            tables_updated.append("invoices")
        elif req["kind"] == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (_add_month(lease["next_due"]), req["ref_id"]))
            tables_updated.append("leases")
        conn.execute(
            "UPDATE approval_requests SET status = 'paid', payment_id = ? WHERE id = ?",
            (payment_id, approval_request_id),
        )
        new_balance = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = ?", (req["account"],)
        ).fetchone()["balance"]
        return {
            "payment_id": payment_id,
            "approval_request_id": approval_request_id,
            "kind": req["kind"],
            "payee": req["payee"],
            "amount": req["amount"],
            "approved_by": req["approved_by"],
            "executed_by": requested_by,
            "new_balance": new_balance,
            "tables_updated": tables_updated,
        }


# ---------------------------------------------------------------------------
# Drafts, approval queue, and ticket decisions
# ---------------------------------------------------------------------------


@mcp.tool
def save_message_draft(
    audience: str,
    recipient: str,
    subject: str,
    body: str,
    author_agent: str,
    ticket_id: int | None = None,
) -> dict:
    """Save a draft message (customer, vendor, or landlord). NEVER sends anything.

    Stores the draft in message_drafts with status 'draft_not_sent' so a
    human can review it. Any older unsent draft to the same recipient for the
    same ticket is marked 'superseded'. The recipient must be a requester on a ticket, a
    vendor, or a landlord already in the database. Nothing is emailed,
    called, or sent.
    """
    author_agent = _check_agent(author_agent)
    if audience not in {"customer", "vendor", "landlord"}:
        raise ValueError("audience must be 'customer', 'vendor', or 'landlord'.")
    with _connect() as conn:
        known = {
            "customer": {r[0] for r in conn.execute("SELECT requester FROM tickets")},
            "vendor": {r[0] for r in conn.execute("SELECT name FROM vendors")},
            "landlord": {r[0] for r in conn.execute("SELECT landlord FROM leases")},
        }[audience]
        if recipient not in known:
            raise ValueError(f"'{recipient}' is not a known {audience} in the database. Known: {sorted(known)}.")
        existing = conn.execute(
            """SELECT id FROM message_drafts
               WHERE ticket_id IS ? AND audience = ? AND recipient = ? AND subject = ? AND body = ?""",
            (ticket_id, audience, recipient, subject, body),
        ).fetchone()
        if existing:
            return {"draft_id": existing["id"], "status": "draft_not_sent", "recipient": recipient,
                    "sent": False, "duplicate": True}
        cur = conn.execute(
            """INSERT INTO message_drafts (ticket_id, audience, recipient, subject, body, author_agent, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft_not_sent')""",
            (ticket_id, audience, recipient, subject, body, author_agent, _now()),
        )
        # A newer draft to the same person about the same ticket replaces the old one, so a human
        # never sends a stale version (e.g. an outdated price).
        superseded = [
            r["id"]
            for r in conn.execute(
                """SELECT id FROM message_drafts WHERE ticket_id IS ? AND audience = ? AND recipient = ?
                   AND status = 'draft_not_sent' AND id != ?""",
                (ticket_id, audience, recipient, cur.lastrowid),
            )
        ]
        if superseded:
            conn.execute(
                f"UPDATE message_drafts SET status = 'superseded' WHERE id IN ({','.join('?' * len(superseded))})",
                superseded,
            )
        return {"draft_id": cur.lastrowid, "status": "draft_not_sent", "recipient": recipient, "sent": False,
                "superseded_draft_ids": superseded}


@mcp.tool
def list_approval_queue(status: str | None = None) -> dict:
    """Approval queue: list payment / PO approval requests and saved message drafts.

    Optional status filter for approval requests ('pending', 'approved',
    'rejected', 'paid'). Use this to see what is waiting on a human and to
    avoid queuing the same payment twice.
    """
    with _connect() as conn:
        q = "SELECT * FROM approval_requests"
        params: tuple = ()
        if status:
            q += " WHERE status = ?"
            params = (status,)
        requests = [dict(r) for r in conn.execute(q + " ORDER BY id", params)]
        drafts = [
            dict(r)
            for r in conn.execute(
                "SELECT id, ticket_id, audience, recipient, subject, body, author_agent, created_at, status FROM message_drafts ORDER BY id"
            )
        ]
        return {"approval_requests": requests, "message_drafts": drafts}


@mcp.tool
def record_ticket_decision(ticket_id: int, status: str, decision: str, decided_by: str) -> dict:
    """Record the Boss's final decision on a ticket and set the ticket's status.

    status: 'in_progress', 'awaiting_approval' (money or a send needs a
    human), or 'resolved'. A ticket with pending approval requests cannot be
    marked 'resolved'. Only the boss may call this. Keeps a history row in
    ticket_decisions.
    """
    decided_by = _check_agent(decided_by)
    if decided_by != "boss":
        raise ValueError("Only the boss records final ticket decisions.")
    if status not in TICKET_STATUSES:
        raise ValueError(f"status must be one of {sorted(TICKET_STATUSES)}.")
    with _connect() as conn:
        if conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found.")
        pending = conn.execute(
            "SELECT COUNT(*) FROM approval_requests WHERE ticket_id = ? AND status IN ('pending', 'approved')",
            (ticket_id,),
        ).fetchone()[0]
        if status == "resolved" and pending:
            raise ValueError(f"Ticket {ticket_id} has {pending} approval request(s) still open. Use 'awaiting_approval'.")
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        cur = conn.execute(
            "INSERT INTO ticket_decisions (ticket_id, status, decision, decided_by, decided_at) VALUES (?, ?, ?, ?, ?)",
            (ticket_id, status, decision, decided_by, _now()),
        )
        return {"ticket_id": ticket_id, "status": status, "decision_id": cur.lastrowid}



# ---------------------------------------------------------------------------
# Human-only actions (dashboard backend). Not in any agent's allowlist.
# ---------------------------------------------------------------------------


@mcp.tool
def human_decide_approval(approval_request_id: int, decision: str, approver: str, reason: str = "") -> dict:
    """HUMAN ONLY: approve or reject a pending payment / PO request.

    decision: 'approve' or 'reject'. approver must be a human's name, never
    an agent name. Approving does not move money by itself; the pay tool
    (pay_approved_request) does that afterward. Only 'pending' requests can be decided.
    """
    approver = approver.strip()
    if not approver:
        raise ValueError("A human approver name is required.")
    if approver.lower() in EXECUTORS:
        raise ValueError(f"'{approver}' is not a human. Only a person can approve or reject a payment.")
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'.")
    with _connect() as conn:
        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_request_id,)).fetchone()
        if req is None:
            raise ValueError(f"Approval request {approval_request_id} not found.")
        if req["status"] != "pending":
            raise ValueError(f"Approval request {approval_request_id} is '{req['status']}', not pending.")
        status = "approved" if decision == "approve" else "rejected"
        memo = req["memo"] + (f" | {status} by {approver}: {reason}" if reason else "")
        conn.execute(
            "UPDATE approval_requests SET status = ?, approved_by = ?, decided_at = ?, memo = ? WHERE id = ?",
            (status, approver, _now(), memo, approval_request_id),
        )
        return {
            "approval_request_id": approval_request_id,
            "status": status,
            "approved_by": approver,
            "kind": req["kind"],
            "payee": req["payee"],
            "amount": req["amount"],
            "ticket_id": req["ticket_id"],
        }


@mcp.tool
def human_reset_database(confirm: str) -> dict:
    """HUMAN ONLY: reset the database for a fresh run. Pass confirm='RESET'.

    Backs up the current database to data/backups/, then restores the 9 shop
    tables from data/campus_customs.db (the original) and empties approval_requests,
    message_drafts and ticket_decisions, all in one transaction.
    """
    if confirm != "RESET":
        raise ValueError("Pass confirm='RESET' to reset the database.")
    if not SEED_DB.exists():
        raise ValueError(f"Seed database not found at {SEED_DB}.")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"pre_reset_{datetime.now():%Y%m%d_%H%M%S}.db"
    with _connect() as conn:
        dest = sqlite3.connect(backup_path)
        try:
            conn.backup(dest)
        finally:
            dest.close()
    with _connect() as conn:
        conn.execute("ATTACH DATABASE ? AS seed", (str(SEED_DB),))
        restored = {}
        for table in SHOP_TABLES:
            conn.execute(f"DELETE FROM main.{table}")
            conn.execute(f"INSERT INTO main.{table} SELECT * FROM seed.{table}")
            restored[table] = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        for table in AGENT_TABLES:
            conn.execute(f"DELETE FROM main.{table}")
        conn.commit()
        conn.execute("DETACH DATABASE seed")
        balance = conn.execute("SELECT name, balance FROM cash_accounts").fetchall()
        tickets = conn.execute("SELECT id, status FROM tickets ORDER BY id").fetchall()
    return {
        "reset": True,
        "backup": str(backup_path),
        "seed": str(SEED_DB),
        "rows_restored": restored,
        "agent_tables_cleared": list(AGENT_TABLES),
        "cash_accounts": [dict(b) for b in balance],
        "tickets": [dict(t) for t in tickets],
    }



@mcp.tool
def human_resolve_ticket(ticket_id: int, closed_by: str, note: str = "") -> dict:
    """HUMAN ONLY: mark a ticket resolved from the dashboard after the agents' run.

    closed_by must be a human's name. Refuses while the ticket still has a
    pending or approved (unpaid) approval request, the same rule the Boss
    follows. Keeps a history row in ticket_decisions.
    """
    closed_by = closed_by.strip()
    if not closed_by:
        raise ValueError("A human name is required to resolve a ticket.")
    if closed_by.lower() in EXECUTORS:
        raise ValueError(f"'{closed_by}' is not a human. Agents record decisions with record_ticket_decision.")
    with _connect() as conn:
        ticket = conn.execute("SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found.")
        if ticket["status"] == "resolved":
            raise ValueError(f"Ticket {ticket_id} is already resolved.")
        open_requests = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM approval_requests WHERE ticket_id = ? AND status IN ('pending', 'approved')",
                (ticket_id,),
            )
        ]
        if open_requests:
            raise ValueError(
                f"Ticket {ticket_id} still has approval request(s) {open_requests} waiting. "
                "Approve and pay, or reject them, before resolving."
            )
        conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
        decision = f"Marked resolved by {closed_by}" + (f": {note}" if note else ".")
        cur = conn.execute(
            "INSERT INTO ticket_decisions (ticket_id, status, decision, decided_by, decided_at) VALUES (?, 'resolved', ?, ?, ?)",
            (ticket_id, decision, closed_by, _now()),
        )
        return {"ticket_id": ticket_id, "status": "resolved", "closed_by": closed_by, "decision_id": cur.lastrowid}


if __name__ == "__main__":
    mcp.run(show_banner=False)
