"""Política de roteamento: transforma uma Decision em uma rota.

O modelo de decisão diz O QUE a fala é; a política decide O QUE FAZER, usando a confiança:
  - decisão "ignore"                    -> NONE
  - confiança < min_confidence          -> depende de low_confidence:
        "ignore"   : descarta (prioriza não acordar à toa — bom para escuta contínua)
        "clarify"  : pede confirmação ao usuário
        "escalate" : manda a decisão para um LLM maior decidir (cascata)
  - caso contrário                      -> rota da taxonomia (HOME_AUTOMATION, MEDIA, TIMERS, LLM, LLM_LARGE)
"""

from __future__ import annotations

from dataclasses import dataclass

from lab.taxonomy import Taxonomy
from lab.types import Decision

LLM_ROUTES = {"LLM", "LLM_LARGE"}


@dataclass
class Policy:
    min_confidence: float = 0.0
    low_confidence: str = "ignore"  # ignore | clarify | escalate
    ignore_key: str = "ignore"


@dataclass
class RouteResult:
    route: str
    reason: str


def route_decision(decision: Decision, taxonomy: Taxonomy, policy: Policy) -> RouteResult:
    if decision.decision == policy.ignore_key:
        return RouteResult("NONE", "decisão: ignorar")
    conf = decision.confidence
    if policy.min_confidence > 0 and conf is not None and conf < policy.min_confidence:
        target = {"ignore": "NONE", "clarify": "CLARIFY", "escalate": "ESCALATE"}[policy.low_confidence]
        return RouteResult(target, f"confiança {conf:.2f} < {policy.min_confidence:.2f}")
    return RouteResult(taxonomy.route(decision.decision), f"decisão: {decision.decision}")
