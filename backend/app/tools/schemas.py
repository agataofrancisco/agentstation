"""Schemas Pydantic de entrada e saida das ferramentas. Entrada rejeita campos extra."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

TICKET_ID = r"^(T|ATL)-\d{1,6}$"
PROCEDURE_ID = r"^(PR|ATL-PR)-\d{2}$"
USER_ID = r"^[a-z0-9._-]{1,64}@[a-z0-9-]{1,32}$"

TicketId = Annotated[str, Field(pattern=TICKET_ID)]
ProcedureId = Annotated[str, Field(pattern=PROCEDURE_ID)]
UserId = Annotated[str, Field(pattern=USER_ID)]
AccountAction = Literal["reset_mfa", "suspend", "unsuspend"]
TicketStatus = Literal["open", "pending", "resolved", "closed"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchTicketsIn(_Input):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=20)


class GetTicketIn(_Input):
    ticket_id: TicketId


class SearchProceduresIn(_Input):
    query: str = Field(min_length=1, max_length=200)


class DraftReplyIn(_Input):
    ticket_id: TicketId
    body: str = Field(min_length=1, max_length=4000)
    citations: list[ProcedureId] = Field(default_factory=list, max_length=10)


class ProposeTicketStatusIn(_Input):
    ticket_id: TicketId
    status: TicketStatus
    justification: str = Field(min_length=1, max_length=1000)


class ProposeAccountActionIn(_Input):
    user_id: UserId
    action: AccountAction
    days: int | None = Field(default=None, ge=1, le=365)
    justification: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(default_factory=list, max_length=10)


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketSummary(_Output):
    id: str
    subject: str
    category: str
    status: str
    priority: str


class TicketDetail(TicketSummary):
    body: str
    requester_email: str


class SearchTicketsOut(_Output):
    items: list[TicketSummary]


class ProcedureItem(_Output):
    id: str
    title: str
    category: str
    body: str
    stance: str | None = None


class SearchProceduresOut(_Output):
    items: list[ProcedureItem]


class DraftOut(_Output):
    draft_id: str
    ticket_id: str
    body: str
    citations: list[str]


class ProposalOut(_Output):
    action: str
    params: dict
    justification: str
    evidence: list[str]
