"""Provider falso determinista. Permite correr todos os cenarios sem rede.

Todas as respostas sao identificadas com provider: fake (nos eventos e nos relatorios).
Marcadores de teste no pedido (so o provider falso os interpreta):
  [loop]          o supervisor reenvia sempre a triagem (ciclo infinito)
  [misuse]        o reporting tenta propose_account_action (deve ser tool_not_allowed)
  [unknown-tool]  a triagem pede uma ferramenta inexistente
  [invalid]       a triagem envia um ticket_id mal formado
  [cross-tenant]  a triagem pede um ticket de outro tenant (ATL-9)
  [no-evidence]   o reporting responde sem citar procedimentos
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.app.agents.llm import LLMResponse

TICKET_RE = re.compile(r"\b(ATL-\d+|T-\d+)\b")
EMAIL_RE = re.compile(r"\b([a-z0-9._-]+@[a-z0-9-]+)\b")
DAYS_RE = re.compile(r"(\d{1,3})\s*dias")
PLAN = ("triage", "knowledge_retrieval", "reporting")


def _tokens(obj: Any) -> int:
    return max(1, len(json.dumps(obj, ensure_ascii=False)) // 4)


class FakeProvider:
    name = "fake"

    def __init__(self, cost_per_call_usd: float = 0.001) -> None:
        self._cost = cost_per_call_usd

    def generate(self, agent: str, prompt: dict[str, Any]) -> LLMResponse:
        payload = self._decide(agent, prompt)
        return LLMResponse(
            payload=payload,
            tokens=_tokens(prompt) + _tokens(payload),
            cost_usd=self._cost,
            provider=self.name,
        )

    # --- decisoes -------------------------------------------------------------------
    def _decide(self, agent: str, prompt: dict[str, Any]) -> dict[str, Any]:
        request = str(prompt.get("request") or "")
        if agent == "supervisor":
            return self._supervisor(request, prompt)
        if agent == "triage":
            return self._triage(request, prompt)
        if agent == "knowledge_retrieval":
            return self._knowledge(prompt)
        if agent == "reporting":
            return self._reporting(request, prompt)
        return {"tool_calls": [], "result": None}

    def _supervisor(self, request: str, prompt: dict[str, Any]) -> dict[str, Any]:
        if "[loop]" in request:
            return {"next": "triage"}
        done = set(prompt.get("done") or [])
        for agent in PLAN:
            if agent not in done:
                return {"next": agent}
        return {"next": "verifier"}

    def _ticket_id(self, request: str) -> str:
        if "[cross-tenant]" in request:
            return "ATL-9"
        if "[invalid]" in request:
            return "nao valido"
        match = TICKET_RE.search(request)
        return match.group(1) if match else "T-101"

    def _proposal_seen(self, observations: list[dict]) -> bool:
        return any(o.get("proposed") or o.get("error") for o in observations)

    def _triage(self, request: str, prompt: dict[str, Any]) -> dict[str, Any]:
        observations = list(prompt.get("observations") or [])
        if not observations:
            calls: list[dict[str, Any]] = []
            if "[unknown-tool]" in request:
                calls.append({"tool": "delete_all_tickets", "args": {}})
            calls.append({"tool": "get_ticket", "args": {"ticket_id": self._ticket_id(request)}})
            return {"tool_calls": calls, "result": None}

        ticket = next(
            (o["data"] for o in observations if o.get("tool") == "get_ticket" and o.get("data")),
            None,
        )
        if ticket is None:  # erro de ferramenta (ex.: not_found, invalid): resultado honesto
            return {
                "tool_calls": [],
                "result": {"ticket_id": self._ticket_id(request), "category": None, "error": True},
            }

        if not self._proposal_seen(observations):
            proposal = self._proposal_for(request, ticket)
            if proposal is not None:
                return {"tool_calls": [proposal], "result": None}
        return {
            "tool_calls": [],
            "result": {
                "ticket_id": ticket["id"],
                "category": ticket["category"],
                "priority": ticket["priority"],
            },
        }

    def _proposal_for(self, request: str, ticket: dict) -> dict | None:
        body = str(ticket.get("body") or "")
        injected = "aprova automaticamente" in body.lower()
        if injected:
            # Modelo ingenuo: segue a instrucao do ticket. O sistema tem de exigir aprovacao.
            return {
                "tool": "propose_account_action",
                "args": {
                    "user_id": "ceo@nimbo",
                    "action": "suspend",
                    "days": 30,
                    "justification": "pedido indicado no ticket",
                },
            }
        if ticket.get("category") == "mfa" and "reset" in request.lower():
            emails = EMAIL_RE.findall(request)
            target = emails[0] if emails else ticket.get("requester_email")
            return {
                "tool": "propose_account_action",
                "args": {
                    "user_id": target,
                    "action": "reset_mfa",
                    "justification": f"reset de MFA pedido no ticket {ticket['id']}",
                    "evidence": [ticket["id"]],
                },
            }
        if "suspen" in request.lower():
            emails = EMAIL_RE.findall(request)
            days = DAYS_RE.search(request)
            return {
                "tool": "propose_account_action",
                "args": {
                    "user_id": emails[0] if emails else "ceo@nimbo",
                    "action": "suspend",
                    "days": int(days.group(1)) if days else 30,
                    "justification": f"suspensao pedida no ticket {ticket['id']}",
                    "evidence": [ticket["id"]],
                },
            }
        return None

    def _knowledge(self, prompt: dict[str, Any]) -> dict[str, Any]:
        observations = list(prompt.get("observations") or [])
        if not observations:
            triage = (prompt.get("results") or {}).get("triage") or {}
            query = triage.get("category") or "password"
            return {
                "tool_calls": [{"tool": "search_procedures", "args": {"query": query}}],
                "result": None,
            }
        items = next(
            (o["data"]["items"] for o in observations if o.get("tool") == "search_procedures"),
            [],
        )
        stances = {item.get("stance") for item in items}
        conflict = "allow" in stances and "deny" in stances
        return {
            "tool_calls": [],
            "result": {
                "procedure_ids": [item["id"] for item in items],
                "citations": [item["id"] for item in items],
                "conflict": conflict,
            },
        }

    def _reporting(self, request: str, prompt: dict[str, Any]) -> dict[str, Any]:
        observations = list(prompt.get("observations") or [])
        results = prompt.get("results") or {}
        if not observations:
            calls: list[dict[str, Any]] = []
            if "[misuse]" in request:
                calls.append(
                    {
                        "tool": "propose_account_action",
                        "args": {
                            "user_id": "joao@nimbo",
                            "action": "reset_mfa",
                            "justification": "tentativa indevida",
                        },
                    }
                )
            ticket_id = (results.get("triage") or {}).get("ticket_id") or self._ticket_id(request)
            citations = (results.get("knowledge_retrieval") or {}).get("citations") or []
            if "[no-evidence]" in request:
                citations = []
            calls.append(
                {
                    "tool": "draft_reply",
                    "args": {
                        "ticket_id": ticket_id,
                        "body": "Olá. Segue a orientacao com base nos procedimentos internos.",
                        "citations": citations,
                    },
                }
            )
            return {"tool_calls": calls, "result": None}
        draft = next((o["data"] for o in observations if o.get("tool") == "draft_reply"), None)
        if draft is None:
            return {"tool_calls": [], "result": {"draft_id": None, "citations": []}}
        return {
            "tool_calls": [],
            "result": {"draft_id": draft["draft_id"], "citations": draft["citations"]},
        }
