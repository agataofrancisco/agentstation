"""Implementacao das 6 ferramentas sobre os dados demo. O tenant vem SEMPRE do contexto."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import or_

from backend.app.store.models import Procedure, Ticket, User
from backend.app.tools import schemas as s
from backend.app.tools.context import ToolContext
from backend.app.tools.errors import ToolError

DEFAULT_SUSPENSION_DAYS = 30


def _scoped(ctx: ToolContext, model: type, object_id: str):
    row = ctx.session.get(model, object_id)
    if row is None or row.tenant_id != ctx.tenant_id:
        raise ToolError("not_found")
    return row


def _ticket_summary(t: Ticket) -> dict[str, Any]:
    return {
        "id": t.id,
        "subject": t.subject,
        "category": t.category,
        "status": t.status,
        "priority": t.priority,
    }


def _procedure(p: Procedure) -> dict[str, Any]:
    return {
        "id": p.id,
        "title": p.title,
        "category": p.category,
        "body": p.body,
        "stance": p.stance,
    }


def search_tickets(ctx: ToolContext, args: s.SearchTicketsIn) -> dict[str, Any]:
    q = args.query
    rows = (
        ctx.session.query(Ticket)
        .filter(Ticket.tenant_id == ctx.tenant_id)
        .filter(
            or_(
                Ticket.subject.icontains(q, autoescape=True),
                Ticket.category.icontains(q, autoescape=True),
                Ticket.body.icontains(q, autoescape=True),
            )
        )
        .order_by(Ticket.id)
        .limit(args.limit)
        .all()
    )
    return {"items": [_ticket_summary(t) for t in rows]}


def get_ticket(ctx: ToolContext, args: s.GetTicketIn) -> dict[str, Any]:
    t = _scoped(ctx, Ticket, args.ticket_id)
    return {**_ticket_summary(t), "body": t.body, "requester_email": t.requester_email}


def search_procedures(ctx: ToolContext, args: s.SearchProceduresIn) -> dict[str, Any]:
    q = args.query
    rows = (
        ctx.session.query(Procedure)
        .filter(Procedure.tenant_id == ctx.tenant_id)
        .filter(
            or_(
                Procedure.category.icontains(q, autoescape=True),
                Procedure.title.icontains(q, autoescape=True),
                Procedure.body.icontains(q, autoescape=True),
            )
        )
        .order_by(Procedure.id)
        .limit(10)
        .all()
    )
    return {"items": [_procedure(p) for p in rows]}


def draft_reply(ctx: ToolContext, args: s.DraftReplyIn) -> dict[str, Any]:
    _scoped(ctx, Ticket, args.ticket_id)
    for proc_id in args.citations:
        proc = ctx.session.get(Procedure, proc_id)
        if proc is None or proc.tenant_id != ctx.tenant_id:
            raise ToolError("invalid_citation")
    digest = hashlib.sha256(f"{args.ticket_id}|{args.body}".encode()).hexdigest()[:16]
    return {
        "draft_id": f"draft-{digest}",
        "ticket_id": args.ticket_id,
        "body": args.body,
        "citations": list(args.citations),
    }


def propose_ticket_status(ctx: ToolContext, args: s.ProposeTicketStatusIn) -> dict[str, Any]:
    _scoped(ctx, Ticket, args.ticket_id)
    return {
        "action": "set_ticket_status",
        "params": {"ticket_id": args.ticket_id, "status": args.status},
        "justification": args.justification,
        "evidence": [args.ticket_id],
    }


def propose_account_action(ctx: ToolContext, args: s.ProposeAccountActionIn) -> dict[str, Any]:
    _scoped(ctx, User, args.user_id)
    action_map = {
        "reset_mfa": "reset_mfa",
        "suspend": "suspend_account",
        "unsuspend": "unsuspend_account",
    }
    params: dict[str, Any] = {"user_id": args.user_id}
    if args.action == "suspend":
        params["days"] = args.days or DEFAULT_SUSPENSION_DAYS
    return {
        "action": action_map[args.action],
        "params": params,
        "justification": args.justification,
        "evidence": list(args.evidence),
    }
