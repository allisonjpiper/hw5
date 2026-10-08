"""
audit.py

Append-only writer for output/audit_trail.json. Every agent loop step goes
through record(); entries are added to the existing JSON array, never
replacing what is already there.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AuditEntry

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
AUDIT_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_AUDIT", DEFAULT_PATH))

_lock = threading.Lock()
SECRET_ENV_VARS = ("PORTKEY_API_KEY",)


def _scrub(text: str) -> str:
    for var in SECRET_ENV_VARS:
        secret = os.environ.get(var)
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def record(
    *,
    run_id: str,
    agent: str,
    event: str,
    loop_id: str | None = None,
    ticket_id: int | None = None,
    depth: int = 0,
    chain: list[str] | None = None,
    step: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    entry = AuditEntry(
        timestamp=datetime.now().isoformat(timespec="milliseconds"),
        run_id=run_id,
        loop_id=loop_id,
        agent=agent,
        event=event,  # type: ignore[arg-type]
        ticket_id=ticket_id,
        depth=depth,
        chain=chain or [],
        step=step,
        detail=detail or {},
    )
    line = json.loads(_scrub(entry.model_dump_json()))
    with _lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        entries: list[Any] = []
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size:
            entries = json.loads(AUDIT_PATH.read_text())
            if not isinstance(entries, list):
                raise RuntimeError(f"{AUDIT_PATH} is not a JSON array; refusing to overwrite it.")
        entries.append(line)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, indent=2))
        tmp.replace(AUDIT_PATH)
