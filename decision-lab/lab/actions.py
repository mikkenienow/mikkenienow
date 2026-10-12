"""Motor de ações: da decisão do roteador a uma ferramenta executada, com as travas no meio.

    entrada -> roteador -> [validação da decisão] -> [escolha da ferramenta] -> [validação dos parâmetros]
            -> [confirmação, se sensível] -> ferramenta -> resultado -> log

O roteador (e5 -> decider) responde "é comigo? qual intenção?". Aqui decidimos, DENTRO da rota escolhida,
qual ferramenta da lista permitida atende o pedido, extraímos os parâmetros com regras determinísticas e
só executamos se tudo validar. Nenhum texto do usuário vira comando: ele só pode selecionar uma ferramenta
existente e preencher parâmetros de tipos fechados.

Seletor de ferramenta (tool_selector):
  rules  regex por ferramenta sobre o texto normalizado; sem custo, mas só entende o que foi previsto
  model  o modelo de decisão escolhe entre as descrições das ferramentas da rota (classes dinâmicas)
  hybrid regras quando alguma casa; senão o modelo

Escopo da escolha (tool_scope):
  route  só as ferramentas da rota que o roteador escolheu (confia na intenção do roteador)
  all    todas as ferramentas permitidas: o roteador decide SE é com o assistente, e este passo decide O QUE
         fazer, podendo corrigir uma intenção errada (ex.: um lembrete que o roteador tomou por pergunta)
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from lab.backends.base import Backend
from lab.tools import NeedsInfo, Tool, ToolRegistry
from lab.tools.builtin import WAKE, ToolContext, norm
from lab.types import Option, Timer

_QUESTION = r"\b(como|qual|quais|quem|quanto|quantos|quantas|quando|onde|porque|por que|o que e|o que sao|pra que|para que)\b"
TOOL_QUESTION = ("A home voice assistant received this request (in Portuguese, automatic transcription, may contain "
                 "errors). Which action fulfils the request?")
# Respostas curtas a um pedido de confirmação. Só valem quando há uma pendência do mesmo cliente; qualquer
# outra frase segue para o roteador normalmente (e a pendência expira sozinha).
_YES = r"sim|s|confirma|confirmo|confirmar|pode|pode fazer|isso|isso mesmo|ok|okay|claro|manda|manda ver|faz isso|positivo|quero"
_NO = r"cancela|cancelar|cancele|deixa|deixa pra la|deixa para la|para|negativo|esquece|quero|precisa|obrigado|obrigada|melhor nao"
YES = rf"(?:(?:{_YES})(?: sim| por favor| pode| confirma| claro)*)"
NO = rf"(?:(?:nao|n)(?: (?:{_NO}))*|(?:{_NO.replace('quero|precisa|obrigado|obrigada|', '')})(?: nao| por favor)*)"


@dataclass
class Selection:
    tool: Tool | None
    method: str                      # only | rules | rules-default | model | model-low-confidence | model-failed
    confidence: float | None = None
    scores: dict[str, float] | None = None
    ms: float = 0.0


@dataclass
class ActionPolicy:
    tool_min_confidence: float = 0.5   # seleção por modelo abaixo disso cai na ferramenta padrão da rota
    confirm_ttl: float = 60.0          # segundos para confirmar uma ação sensível


class Planner:
    def __init__(self, registry: ToolRegistry, selector: str = "rules", backend: Backend | None = None,
                 min_confidence: float = 0.5, scope: str = "route") -> None:
        if scope not in ("route", "all"):
            raise ValueError(f"tool_scope inválido: {scope}")
        self.scope = scope
        if selector not in ("rules", "model", "hybrid"):
            raise ValueError(f"tool_selector inválido: {selector}")
        if selector != "rules" and backend is None:
            raise ValueError(f"tool_selector={selector} precisa de um backend de decisão")
        self.registry, self.selector, self.backend, self.min_confidence = registry, selector, backend, min_confidence

    def _by_rules(self, text: str, candidates: list[Tool], route: str) -> Selection:
        t = norm(text)
        for tool in candidates:
            if tool.keywords and re.search(tool.keywords, t):
                return Selection(tool, "rules")
        return Selection(self.registry.default_for(route), "rules-default")

    def _by_model(self, text: str, candidates: list[Tool], route: str) -> Selection:
        assert self.backend is not None
        if re.search(_QUESTION, norm(text)):  # pergunta ("como faço pra...") nunca é pedido sem ferramenta
            candidates = [t for t in candidates if t.kind != "unsupported"]
        options = [Option(t.name, t.description_en) for t in candidates]
        try:
            with Timer() as timer:
                decision = self.backend.decide(text, options, TOOL_QUESTION)
        except Exception:  # servidor do modelo fora do ar: não trava o assistente, cai nas regras
            fallback = self._by_rules(text, candidates, route)
            return Selection(fallback.tool, "model-failed")
        chosen = self.registry.get(decision.decision)  # ToolNotAllowed se o modelo devolver algo fora da lista
        if decision.confidence is not None and decision.confidence < self.min_confidence:
            return Selection(self.registry.default_for(route), "model-low-confidence", decision.confidence,
                             decision.scores, timer.ms)
        return Selection(chosen, "model", decision.confidence, decision.scores, timer.ms)

    def unsupported_for(self, text: str) -> Tool | None:
        """A fala pede algo de uma família que não existe (e-mail, ligação, compra, Spotify…)? Regra, não modelo."""
        t = norm(text)
        return next((x for x in self.registry.all() if x.kind == "unsupported" and x.keywords and re.search(x.keywords, t)), None)

    def select(self, text: str, route: str) -> Selection:
        if not self.registry.for_route(route):
            return Selection(None, "no-tool-for-route")
        gap = self.unsupported_for(text)  # vale em qualquer rota: "não sei fazer" não depende da intenção do roteador
        if gap is not None:
            return Selection(gap, "rules-unsupported")
        candidates = self.registry.all() if self.scope == "all" else self.registry.for_route(route)
        if len(candidates) == 1:
            return Selection(candidates[0], "only")
        if self.selector == "rules":
            return self._by_rules(text, candidates, route)
        if self.selector == "hybrid":
            # regras só dentro da rota do roteador: uma regra que casa em OUTRA rota não é evidência
            # suficiente ("pode parar o alarme" casaria com pausar a mídia). Dois sinais concordando -> age.
            ruled = self._by_rules(text, self.registry.for_route(route), route)
            if ruled.method == "rules":
                return ruled
        return self._by_model(text, candidates, route)


@dataclass
class Pending:
    token: str
    tool: Tool
    args: dict[str, Any]
    client: str
    text: str
    expires: float
    prompt: str


@dataclass
class ActionEngine:
    registry: ToolRegistry
    planner: Planner
    ctx: ToolContext
    valid_decisions: set[str]
    llm: Callable[[str, bool, str], None] | None = None   # (fala, modelo_grande, id do registro) -> responde assíncrono
    policy: ActionPolicy = field(default_factory=ActionPolicy)
    pending: dict[str, Pending] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------------ fluxo principal
    def act(self, text: str, decision: str, route: str, client: str, record_id: str) -> dict[str, Any]:
        """Decisão já roteada -> resultado da ferramenta. Nunca levanta exceção: todo desfecho vira um status."""
        if decision not in self.valid_decisions:
            return self._out("rejected", say="Não entendi o pedido.", errors=[f"decisão fora da taxonomia: {decision!r}"])
        if route == "NONE":
            # O roteador disse "não é comigo". Mas se começa com "Alexa," (chamou pelo nome) e pede algo que não existe,
            # a pessoa merece saber que eu entendi e não sei fazer, em vez de silêncio.
            gap = self.planner.unsupported_for(text) if re.match(WAKE, text.strip(), flags=re.I) else None
            if gap is not None:
                return self._run(gap, {}, text, record_id, selection={"method": "rules-unsupported-addressed",
                                                                      "confidence": None, "scores": None, "ms": 0.0})
            return self._out("ignored")
        if route in ("CLARIFY", "ESCALATE"):
            return self._out("clarify", say="Não tenho certeza do que você pediu. Pode repetir?")
        try:
            selection = self.planner.select(text, route)
        except Exception as error:  # inclui ToolNotAllowed: o modelo apontou algo fora da lista
            return self._out("rejected", say="Não posso fazer isso.", errors=[f"seleção de ferramenta inválida: {error!r}"])
        tool = selection.tool
        info = {"method": selection.method, "confidence": selection.confidence, "scores": selection.scores,
                "ms": round(selection.ms, 1)}
        if tool is None:
            return self._out("rejected", say="Não tenho uma ferramenta para isso.", selection=info,
                             errors=[f"nenhuma ferramenta permitida para a rota {route}"])
        args = {k: v for k, v in tool.extract(text).items() if v is not None}
        errors = tool.validate(args)
        if errors:
            return self._out("needs_info", tool, args, selection=info, errors=errors,
                             say="Não consegui fazer: " + "; ".join(errors) + ".")
        if tool.is_sensitive(args):
            pending = self._hold(tool, args, client, text)
            return self._out("needs_confirmation", tool, args, selection=info, say=pending.prompt,
                             confirm={"token": pending.token, "prompt": pending.prompt,
                                      "expires_in": int(self.policy.confirm_ttl)})
        return self._run(tool, args, text, record_id, selection=info)

    def _run(self, tool: Tool, args: dict[str, Any], text: str, record_id: str, **extra: Any) -> dict[str, Any]:
        if tool.name.startswith("llm."):
            if self.llm is None:
                return self._out("failed", tool, args, say="O modelo de linguagem não está disponível.", **extra)
            self.llm(text, tool.name == "llm.answer_large", record_id)
            return self._out("answering", tool, args, say=tool.say(args, {}), **extra)
        if tool.kind == "unsupported":  # entendi que era comigo, mas não existe ferramenta para isso
            return self._out("unsupported", tool, args, say=(
                f"Entendi que o pedido era para mim, mas ainda não sei fazer isso: “{text.strip()}”. "
                "Pergunte “o que você sabe fazer?” para ver o que eu faço."), **extra)
        try:
            with Timer() as timer:
                result = tool.handler(args, self.ctx)
            out = self._out("executed", tool, args, result=result, say=tool.say(args, result), ms=round(timer.ms, 2), **extra)
            if isinstance(result, dict) and "real" in result:
                out["real"] = bool(result["real"])  # o player pode estar no modo simulado mesmo com a ferramenta "real"
            return out
        except NeedsInfo as question:
            return self._out("needs_info", tool, args, say=str(question), errors=[str(question)], **extra)
        except Exception as error:
            return self._out("failed", tool, args, say="Algo deu errado ao executar.", errors=[repr(error)[:300]], **extra)

    @staticmethod
    def _out(status: str, tool: Tool | None = None, args: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"status": status, "name": tool.name if tool else None, "args": args or {}}
        if tool:
            out.update(real=tool.real, sensitive=tool.is_sensitive(args or {}))
        out.update(extra)
        return out

    # ------------------------------------------------------------------ confirmação de ações sensíveis
    def _hold(self, tool: Tool, args: dict[str, Any], client: str, text: str) -> Pending:
        prompt = tool.confirm_text(args) if tool.confirm_text else f"Confirma {tool.description_pt.lower()}?"
        pending = Pending(uuid.uuid4().hex[:12], tool, args, client, text, time.time() + self.policy.confirm_ttl, prompt)
        with self.lock:
            for token in [t for t, p in self.pending.items() if p.client == client or p.expires < time.time()]:
                del self.pending[token]      # uma pendência por cliente; a nova substitui a anterior
            self.pending[pending.token] = pending
        return pending

    def confirm(self, token: str, approve: bool, client: str, record_id: str) -> dict[str, Any]:
        with self.lock:
            pending = self.pending.pop(token, None)
        if pending is None:
            return self._out("rejected", say="Não há nada esperando confirmação.", errors=["token desconhecido ou já usado"])
        if pending.expires < time.time():
            return self._out("expired", pending.tool, pending.args, say="A confirmação expirou. Peça de novo.")
        if pending.client != client:
            with self.lock:
                self.pending[token] = pending   # outro aparelho não confirma por você; a pendência continua valendo
            return self._out("rejected", pending.tool, pending.args, say="Só quem pediu pode confirmar.",
                             errors=["confirmação vinda de outro cliente"])
        if not approve:
            return self._out("cancelled", pending.tool, pending.args, say="Cancelado.")
        errors = pending.tool.validate(pending.args)   # revalida: nada muda entre pedir e confirmar, mas não custa
        if errors:
            return self._out("rejected", pending.tool, pending.args, errors=errors, say="Não posso fazer isso.")
        return self._run(pending.tool, pending.args, pending.text, record_id, confirmed=True)

    def spoken_confirmation(self, text: str, client: str, record_id: str) -> dict[str, Any] | None:
        """"sim" / "cancela" logo depois de um pedido sensível do MESMO cliente. Fora disso, devolve None."""
        with self.lock:
            pending = next((p for p in self.pending.values() if p.client == client and p.expires >= time.time()), None)
        if pending is None:
            return None
        t = re.sub(r"[^\w\s]", " ", norm(re.sub(WAKE, "", text.strip(), flags=re.I)))
        t = re.sub(r"\s+", " ", t).strip()
        if re.fullmatch(YES, t):
            return self.confirm(pending.token, True, client, record_id)
        if re.fullmatch(NO, t):
            return self.confirm(pending.token, False, client, record_id)
        return None
