import { useEffect, useRef, type ReactNode } from "react";
import { agentInfo, STATUS_LABEL } from "../format";
import type { TicketStatus } from "../types";

export function StatusBadge({ status }: { status: TicketStatus }) {
  return <span className={`badge ${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function Avatar({ agent, size = 26 }: { agent: string; size?: number }) {
  const info = agentInfo(agent);
  return (
    <span className="avatar" style={{ background: info.color, width: size, height: size }} title={info.label} aria-hidden>
      {info.initials}
    </span>
  );
}

export function Modal({
  title,
  children,
  footer,
  onClose,
}: {
  title: string;
  children: ReactNode;
  footer: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("input, textarea, button")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <header>
          <h3>{title}</h3>
        </header>
        <div className="body">{children}</div>
        <footer>{footer}</footer>
      </div>
    </div>
  );
}

export function NameField({ value, onChange, label = "Your name" }: { value: string; onChange: (v: string) => void; label?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        className="input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g. Allison Piper"
        autoComplete="name"
      />
      <span className="hint" style={{ fontWeight: 400, marginTop: 4 }}>
        Recorded as the human approver in the database and audit trail.
      </span>
    </label>
  );
}

export function Empty({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="icon" aria-hidden>
        {icon}
      </div>
      <div style={{ fontWeight: 600, color: "var(--ink-2)" }}>{title}</div>
      {children && <div style={{ marginTop: 4 }}>{children}</div>}
    </div>
  );
}

export type Toast = { id: number; kind: "success" | "error" | "info"; text: string };

export function Toasts({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: number) => void }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span>{t.kind === "success" ? "✓" : t.kind === "error" ? "!" : "i"}</span>
          <span>{t.text}</span>
          <button onClick={() => dismiss(t.id)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
