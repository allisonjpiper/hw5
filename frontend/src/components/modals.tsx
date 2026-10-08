import { useState } from "react";
import { KIND_LABEL, money } from "../format";
import type { ApprovalRequest, Ticket } from "../types";
import { Modal, NameField } from "./ui";

const AGENT_WORDS = ["boss", "inventory", "accounting", "facilities", "customer_service", "dashboard"];
const isHumanName = (n: string) => n.trim().length > 1 && !AGENT_WORDS.includes(n.trim().toLowerCase());

type Submit = (name: string, text: string) => Promise<void>;

function useSubmit(onSubmit: Submit, onClose: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (name: string, text: string) => {
    setBusy(true);
    setError(null);
    try {
      await onSubmit(name.trim(), text.trim());
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

export function ApproveModal({
  request,
  checking,
  defaultName,
  onSubmit,
  onClose,
}: {
  request: ApprovalRequest;
  checking: number | null;
  defaultName: string;
  onSubmit: Submit;
  onClose: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSubmit(onSubmit, onClose);
  const after = checking == null ? null : checking - request.amount;
  return (
    <Modal
      title={`Approve & pay request #${request.id}?`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn success" disabled={busy || !isHumanName(name) || (after != null && after < 0)} onClick={() => run(name, reason)}>
            {busy ? <span className="spinner" /> : "✓"} Approve and pay {money(request.amount)}
          </button>
        </>
      }
    >
      <p style={{ margin: "0 0 4px" }}>
        <b>{KIND_LABEL[request.kind]}</b> to <b>{request.payee}</b>
        {request.ticket_id ? <> · ticket #{request.ticket_id}</> : null}
      </p>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        {request.memo}
      </p>
      <div className="impact">
        <div>
          <div className="hint">Checking now</div>
          <b>{money(checking)}</b>
        </div>
        <span className="muted">→</span>
        <div>
          <div className="hint">After payment</div>
          <b className={`after ${after != null && after < 0 ? "neg" : ""}`}>{money(after)}</b>
        </div>
      </div>
      {after != null && after < 0 && <div className="callout danger">Not enough cash. The shop doesn't go into debt, so this payment can't be made.</div>}
      <div className="callout info">
        This moves real money in the shop's books: it records a payment, lowers the checking balance, and marks the
        {request.kind === "rent" ? " rent as paid for this period" : request.kind === "invoice" ? " invoice as paid" : " purchase order as paid"}.
      </div>
      <NameField value={name} onChange={setName} />
      <label className="field">
        <span>Note (optional)</span>
        <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why you're approving" />
      </label>
      {error && <div className="callout danger">{error}</div>}
    </Modal>
  );
}

export function RejectModal({
  request,
  defaultName,
  onSubmit,
  onClose,
}: {
  request: ApprovalRequest;
  defaultName: string;
  onSubmit: Submit;
  onClose: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSubmit(onSubmit, onClose);
  return (
    <Modal
      title={`Reject request #${request.id}?`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn danger solid" disabled={busy || !isHumanName(name)} onClick={() => run(name, reason)}>
            {busy && <span className="spinner" />} Reject
          </button>
        </>
      }
    >
      <p style={{ marginTop: 0 }}>
        {KIND_LABEL[request.kind]} of <b>{money(request.amount)}</b> to <b>{request.payee}</b>. No money will move.
      </p>
      <NameField value={name} onChange={setName} />
      <label className="field">
        <span>Reason</span>
        <textarea className="textarea" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Hold until rent clears" />
      </label>
      {error && <div className="callout danger">{error}</div>}
    </Modal>
  );
}

export function ResolveModal({
  ticket,
  defaultName,
  onSubmit,
  onClose,
}: {
  ticket: Ticket;
  defaultName: string;
  onSubmit: Submit;
  onClose: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [note, setNote] = useState("");
  const { busy, error, run } = useSubmit(onSubmit, onClose);
  return (
    <Modal
      title={`Mark ticket #${ticket.id} resolved?`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn success" disabled={busy || !isHumanName(name)} onClick={() => run(name, note)}>
            {busy && <span className="spinner" />} Mark resolved
          </button>
        </>
      }
    >
      <p style={{ marginTop: 0 }}>
        {ticket.subject} · {ticket.requester}
      </p>
      {ticket.draft_ids.length > 0 && (
        <div className="callout warn">
          Agents never send messages. Before closing, make sure you've sent the {ticket.draft_ids.length === 1 ? "draft" : "drafts"} for
          this ticket yourself.
        </div>
      )}
      <NameField value={name} onChange={setName} />
      <label className="field">
        <span>Closing note (optional)</span>
        <textarea className="textarea" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Customer emailed, rent paid" />
      </label>
      {error && <div className="callout danger">{error}</div>}
    </Modal>
  );
}

export function ResetModal({ onSubmit, onClose }: { onSubmit: () => Promise<void>; onClose: () => void }) {
  const [typed, setTyped] = useState("");
  const { busy, error, run } = useSubmit(() => onSubmit(), onClose);
  return (
    <Modal
      title="Reset the shop database?"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn danger solid" disabled={busy || typed !== "RESET"} onClick={() => run("", "")}>
            {busy && <span className="spinner" />} Reset database
          </button>
        </>
      }
    >
      <p style={{ marginTop: 0 }}>This starts a fresh run:</p>
      <ul className="clean">
        <li>All tickets go back to open</li>
        <li>Checking returns to the original balance, and payments are cleared</li>
        <li>Approval requests, drafts, and decisions are removed</li>
      </ul>
      <div className="callout info">A backup of the current database is saved first, and the audit trail is kept.</div>
      <label className="field">
        <span>
          Type <code>RESET</code> to confirm
        </span>
        <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="RESET" />
      </label>
      {error && <div className="callout danger">{error}</div>}
    </Modal>
  );
}
