"""Servidor do laboratório: API de decisão + roteamento + log + eventos em tempo real + UI.

  uvicorn lab.server:app --port 8000      (ou: scripts/lab.sh)

POST /v1/decide  {"input": "...", "options": [...]|{...}?, "question": "..."?, "backend": "..."?}
POST /v1/route   {"input": "...", "backend"?, "min_confidence"?, "low_confidence"?, "execute"?: true}
POST /v1/act     {"input": "...", "client"?}   decisão -> ferramenta permitida -> resultado (lab/actions.py)
POST /v1/act/confirm {"token", "approve"}     confirma ou recusa uma ação sensível | GET /v1/tools
GET  /v1/backends | /v1/state | /v1/log?limit= | /v1/stats | /v1/events (SSE) | /  (UI)
POST /v1/client_timing | GET /v1/client_timings   (Fase 3: ida-e-volta medida no cliente)
POST /v1/feedback | GET /v1/feedback               (julgamento humano de cada decisão, pela UI)
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from lab import backends as registry
from lab.actions import ActionEngine, ActionPolicy, Planner
from lab.backends.base import Backend
from lab.executors import Home, LlmExecutor
from lab.router import LLM_ROUTES, Policy, route_decision
from lab.taxonomy import ROOT, Taxonomy
from lab.tools.builtin import ToolContext, build_registry
from lab.types import normalize_options

CONFIG = registry.load_config()
# LAB_BACKEND troca o backend padrão sem editar o YAML (ex.: cascade-e5-decider-gguf quando só o decider GGUF está no ar)
if os.environ.get("LAB_BACKEND"):
    if os.environ["LAB_BACKEND"] not in CONFIG["backends"]:
        raise SystemExit(f"LAB_BACKEND={os.environ['LAB_BACKEND']}: backend desconhecido (config/backends.yaml)")
    CONFIG["default_backend"] = os.environ["LAB_BACKEND"]
TAXONOMY = Taxonomy.load()
LOG_PATH = ROOT / "runs" / "decisions.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Decision Lab", version="0.1.0")
_backends: dict[str, Backend] = {}
_backend_lock = threading.Lock()
_home = Home()
_stats: dict[str, Any] = {"decisions": 0, "routes": {}, "llm_calls": 0, "llm_calls_avoided": 0,
                          "decision_ms_total": 0.0, "llm_ms_total": 0.0, "tools": {}}
_subscribers: set[asyncio.Queue[str]] = set()
_loop: asyncio.AbstractEventLoop | None = None
_started = time.time()
_client_timings: list[dict[str, Any]] = []
_preload_state: dict[str, Any] = {"status": "off"}
_feedback: dict[str, dict[str, Any]] = {}
_engine: ActionEngine | None = None
_engine_lock = threading.Lock()
_log_lock = threading.Lock()


def get_backend(name: str | None) -> Backend:
    name = name or CONFIG["default_backend"]
    if name not in CONFIG["backends"]:
        raise HTTPException(404, f"backend desconhecido: {name}. Veja GET /v1/backends")
    with _backend_lock:  # carregamento preguiçoso: só sobe na memória o que for usado
        if name not in _backends:
            _backends[name] = registry.create(name, CONFIG)
        return _backends[name]


def publish(event: dict[str, Any]) -> None:
    if _loop is None:
        return
    payload = json.dumps(event, ensure_ascii=False)
    for queue in list(_subscribers):
        _loop.call_soon_threadsafe(queue.put_nowait, payload)


def log(record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _log_lock:  # decisões, respostas do LLM e timers gravam de threads diferentes
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)


class DecideRequest(BaseModel):
    input: str
    options: Any = None
    question: str | None = None
    backend: str | None = None


class RouteRequest(BaseModel):
    input: str
    backend: str | None = None
    min_confidence: float = 0.0
    low_confidence: str = "ignore"
    execute: bool = True
    wait_llm: bool = False
    source: str = "api"


def _decide(req: DecideRequest) -> tuple[Backend, Any, str]:
    backend = get_backend(req.backend)
    options = normalize_options(req.options) if req.options is not None else TAXONOMY.options(backend.option_lang)
    question = req.question or TAXONOMY.question(backend.option_lang)
    try:
        decision = backend.decide(req.input, options, question)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return backend, decision, question


def _record(req_input: str, decision: Any, route: str, reason: str, extra: dict[str, Any]) -> dict[str, Any]:
    record = {"id": uuid.uuid4().hex[:12], "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "t": round(time.time() - _started, 3), "input": req_input, **decision.to_dict(),
              "route": route, "route_reason": reason, **extra}
    _stats["decisions"] += 1
    _stats["routes"][route] = _stats["routes"].get(route, 0) + 1
    _stats["decision_ms_total"] += decision.latency_ms
    log(record)
    publish({"type": "decision", **record})
    return record


@app.on_event("startup")
async def startup() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    if os.environ.get("LAB_PRELOAD", "1") == "1":
        threading.Thread(target=_preload, daemon=True).start()


def _preload() -> None:
    """Carrega e aquece o backend padrão ao subir: sem isso a 1ª fala espera ~20 s (modelo + fit + cache de schema)."""
    _preload_state["status"] = "loading"
    try:
        backend = get_backend(None)
        options, question = TAXONOMY.options(backend.option_lang), TAXONOMY.question(backend.option_lang)
        for text in ("Alexa, acende a luz da sala", "hum, sei lá", "hum, sei lá"):  # a 2ª escala a cascata
            backend.decide(text, options, question)
        engine = get_engine()  # e o schema da escolha de ferramenta (um prefixo novo = segundos na 1ª vez)
        for route in ("LLM", "MEDIA", "TIMERS", "HOME_AUTOMATION"):
            engine.planner.select("hum, sei lá", route)
        _preload_state["status"] = "ready"
    except Exception as error:  # servidor do modelo fora do ar: a API sobe mesmo assim e o erro aparece no /health
        _preload_state.update(status="failed", error=repr(error)[:300])


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "default_backend": CONFIG["default_backend"], "loaded": sorted(_backends),
            "preloading": _preload_state["status"] == "loading", "preload": _preload_state}


@app.get("/v1/backends")
def list_backends() -> dict[str, Any]:
    out = {}
    for name, spec in CONFIG["backends"].items():
        out[name] = {"type": spec["type"], "model": spec.get("model"), "loaded": name in _backends,
                     "option_lang": spec.get("option_lang", "pt")}
    return {"default": CONFIG["default_backend"], "backends": out}


@app.post("/v1/decide")
async def decide(req: DecideRequest) -> dict[str, Any]:
    backend, decision, _ = await run_in_threadpool(_decide, req)
    is_taxonomy = req.options is None
    route = route_decision(decision, TAXONOMY, Policy()) if is_taxonomy else None
    return _record(req.input, decision, route.route if route else "-", route.reason if route else "opções customizadas",
                   {"source": "decide"})


def _execute(record: dict[str, Any], route: str, text: str, wait_llm: bool) -> dict[str, Any]:
    if route == "HOME_AUTOMATION":
        return {"action": _home.home_automation(text)}
    if route == "MEDIA":
        return {"action": _home.media_control(text)}
    if route == "TIMERS":
        return {"action": _home.timer(text)}
    if route in LLM_ROUTES:
        key = "llm_large_executor" if route == "LLM_LARGE" else "llm_executor"
        spec = CONFIG["backends"][CONFIG[key]]
        executor = LlmExecutor(spec["url"], spec["model"])

        def run() -> None:
            result = executor.answer(text)
            _stats["llm_calls"] += 1
            _stats["llm_ms_total"] += result["llm_latency_ms"]
            log({"type": "llm_answer", "decision_id": record["id"], **result})
            publish({"type": "llm_answer", "decision_id": record["id"], **result})

        if wait_llm:
            run()
            return {"action": "llm_answered"}
        threading.Thread(target=run, daemon=True).start()
        return {"action": "llm_called_async"}
    _stats["llm_calls_avoided"] += 1
    return {"action": None}


@app.post("/v1/route")
async def route(req: RouteRequest) -> dict[str, Any]:
    if req.low_confidence not in ("ignore", "clarify", "escalate"):
        raise HTTPException(422, "low_confidence: ignore|clarify|escalate")
    backend, decision, _ = await run_in_threadpool(_decide, DecideRequest(input=req.input, backend=req.backend))
    result = route_decision(decision, TAXONOMY, Policy(req.min_confidence, req.low_confidence))
    record = _record(req.input, decision, result.route, result.reason, {"source": req.source})
    if req.execute:
        outcome = await run_in_threadpool(_execute, record, result.route, req.input, req.wait_llm)
        record.update(outcome)
        if outcome.get("action") not in (None, "llm_called_async", "llm_answered"):
            publish({"type": "state", **_home.snapshot()})
    return record


# ----------------------------------------------------------------------------- ações reais (lab/actions.py)
class ActRequest(BaseModel):
    input: str
    backend: str | None = None
    min_confidence: float = 0.0
    low_confidence: str = "ignore"
    client: str | None = None   # identifica quem pediu (para a confirmação); padrão: IP
    source: str = "api"


class ConfirmRequest(BaseModel):
    token: str
    approve: bool = True
    client: str | None = None


def _llm_answer(text: str, large: bool, record_id: str) -> None:
    spec = CONFIG["backends"][CONFIG["llm_large_executor" if large else "llm_executor"]]
    executor = LlmExecutor(spec["url"], spec["model"])

    def run() -> None:
        try:
            result = executor.answer(text)
        except Exception as error:  # servidor do LLM fora do ar: avisa a UI em vez de deixar "pensando…" para sempre
            result = {"answer": "Não consegui responder: o modelo de linguagem não está no ar.", "llm": spec["model"],
                      "llm_latency_ms": 0, "error": repr(error)[:200]}
        _stats["llm_calls"] += 1
        _stats["llm_ms_total"] += result["llm_latency_ms"]
        log({"type": "llm_answer", "decision_id": record_id, **result})
        publish({"type": "llm_answer", "decision_id": record_id, **result})

    threading.Thread(target=run, daemon=True).start()


def get_engine() -> ActionEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            settings = CONFIG.get("tools", {})
            selector = os.environ.get("LAB_TOOL_SELECTOR", settings.get("selector", "rules"))
            backend = get_backend(settings.get("selector_backend")) if selector != "rules" else None
            registry = build_registry()
            ctx = ToolContext(home=_home, notes_path=ROOT / "runs" / "notes.jsonl", publish=publish, log=log)
            scope = os.environ.get("LAB_TOOL_SCOPE", settings.get("scope", "route"))
            _engine = ActionEngine(registry, Planner(registry, selector, backend, settings.get("min_confidence", 0.5), scope),
                                   ctx, set(TAXONOMY.keys), llm=_llm_answer,
                                   policy=ActionPolicy(confirm_ttl=settings.get("confirm_ttl", 60)))
        return _engine


def _finish_action(record: dict[str, Any]) -> dict[str, Any]:
    status = record["tool"]["status"]
    _stats["tools"][status] = _stats["tools"].get(status, 0) + 1
    log(record)
    publish({"type": "decision", **record})
    if status == "executed":
        publish({"type": "state", **_home.snapshot()})
    return record


@app.get("/v1/tools")
def list_tools() -> dict[str, Any]:
    engine = get_engine()
    return {"selector": engine.planner.selector, "scope": engine.planner.scope, "tools": engine.registry.describe()}


@app.get("/v1/notes")
def notes() -> dict[str, Any]:
    return get_engine().registry.get("note.list").handler({}, get_engine().ctx)


@app.post("/v1/act")
async def act(req: ActRequest, request: Request) -> dict[str, Any]:
    """entrada -> roteador -> validação -> ferramenta permitida -> resultado -> log."""
    if req.low_confidence not in ("ignore", "clarify", "escalate"):
        raise HTTPException(422, "low_confidence: ignore|clarify|escalate")
    client = req.client or (request.client.host if request.client else "?")
    record_id = uuid.uuid4().hex[:12]
    base = {"id": record_id, "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "t": round(time.time() - _started, 3), "input": req.input, "source": req.source, "client": client}
    engine = await run_in_threadpool(get_engine)
    # "sim" / "cancela" respondendo a uma ação sensível pendente deste cliente: não passa pelo roteador
    spoken = await run_in_threadpool(engine.spoken_confirmation, req.input, client, record_id)
    if spoken is not None:
        return _finish_action({**base, "decision": "confirmation", "confidence": None, "scores": None, "score_kind": "none",
                               "latency_ms": 0.0, "backend": "-", "model": "-", "metadata": {}, "route": "CONFIRM",
                               "route_reason": "resposta a um pedido de confirmação", "tool": spoken, "total_ms": 0.0})
    backend, decision, _ = await run_in_threadpool(_decide, DecideRequest(input=req.input, backend=req.backend))
    result = route_decision(decision, TAXONOMY, Policy(req.min_confidence, req.low_confidence))
    started = time.perf_counter()
    tool = await run_in_threadpool(engine.act, req.input, decision.decision, result.route, client, record_id)
    action_ms = (time.perf_counter() - started) * 1000
    _stats["decisions"] += 1
    _stats["routes"][result.route] = _stats["routes"].get(result.route, 0) + 1
    _stats["decision_ms_total"] += decision.latency_ms
    if result.route not in LLM_ROUTES or tool["status"] != "answering":
        _stats["llm_calls_avoided"] += 1
    return _finish_action({**base, **decision.to_dict(), "route": result.route, "route_reason": result.reason,
                           "tool": tool, "action_ms": round(action_ms, 2),
                           "total_ms": round(decision.latency_ms + action_ms, 2)})


@app.post("/v1/act/confirm")
async def act_confirm(req: ConfirmRequest, request: Request) -> dict[str, Any]:
    client = req.client or (request.client.host if request.client else "?")
    record_id = uuid.uuid4().hex[:12]
    engine = await run_in_threadpool(get_engine)
    tool = await run_in_threadpool(engine.confirm, req.token, req.approve, client, record_id)
    record = {"type": "tool_confirmation", "id": record_id, "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "client": client, "approve": req.approve, "tool": tool}
    _stats["tools"][tool["status"]] = _stats["tools"].get(tool["status"], 0) + 1
    log(record)
    if tool["status"] == "executed":
        publish({"type": "state", **_home.snapshot()})
    return record


@app.get("/v1/state")
def state() -> dict[str, Any]:
    return _home.snapshot()


@app.get("/v1/stats")
def stats() -> dict[str, Any]:
    n = max(1, _stats["decisions"])
    return {**_stats, "mean_decision_ms": round(_stats["decision_ms_total"] / n, 1),
            "mean_llm_ms": round(_stats["llm_ms_total"] / max(1, _stats["llm_calls"]), 1)}


class Feedback(BaseModel):
    decision_id: str
    correct: bool
    expected: str | None = None  # a classe certa, quando o usuário marca que o modelo errou
    input: str | None = None
    decision: str | None = None
    backend: str | None = None


@app.post("/v1/feedback")
def feedback(item: Feedback, request: Request) -> dict[str, Any]:
    """Julgamento humano de uma decisão (👍/👎 na UI). Vira dado rotulado real em runs/decisions.jsonl."""
    record = {"type": "feedback", "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "client": request.client.host if request.client else "?", **item.model_dump()}
    _feedback[item.decision_id] = record  # o último julgamento de uma decisão substitui o anterior
    log(record)
    return feedback_summary()


@app.get("/v1/feedback")
def feedback_summary() -> dict[str, Any]:
    rows = list(_feedback.values())
    wrong = [r for r in rows if not r["correct"]]
    return {"n": len(rows), "correct": len(rows) - len(wrong), "wrong": len(wrong),
            "false_activations": sum(r.get("expected") == "ignore" for r in wrong),
            "missed": sum(r.get("decision") == "ignore" for r in wrong)}


class ClientTiming(BaseModel):
    kind: str = "route"  # route: uma fala enviada pela UI | ping: GET /health, só a rede
    round_trip_ms: float
    decision_ms: float = 0.0
    decision_id: str | None = None


@app.post("/v1/client_timing")
def client_timing(timing: ClientTiming, request: Request) -> dict[str, Any]:
    """Fase 3: o cliente (celular) informa quanto esperou; a diferença para o tempo de decisão é rede + servidor."""
    record = {"type": "client_timing", "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "client": request.client.host if request.client else "?",
              "user_agent": request.headers.get("user-agent", "")[:160], **timing.model_dump(),
              "overhead_ms": round(timing.round_trip_ms - timing.decision_ms, 2)}
    _client_timings.append(record)
    log(record)
    return record


@app.get("/v1/client_timings")
def client_timings() -> dict[str, Any]:
    """Resumo por cliente e tipo: mediana e p95 da ida-e-volta e do acréscimo sobre o tempo de decisão."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in _client_timings:
        groups.setdefault(f"{r['client']} {r['kind']}", []).append(r)

    def pct(values: list[float], q: float) -> float:
        values = sorted(values)
        return round(values[min(len(values) - 1, int(q * len(values)))], 1)

    return {key: {"n": len(rows), "user_agent": rows[-1]["user_agent"],
                  "round_trip_p50_ms": pct([r["round_trip_ms"] for r in rows], 0.5),
                  "round_trip_p95_ms": pct([r["round_trip_ms"] for r in rows], 0.95),
                  "decision_p50_ms": pct([r["decision_ms"] for r in rows], 0.5),
                  "overhead_p50_ms": pct([r["overhead_ms"] for r in rows], 0.5),
                  "overhead_p95_ms": pct([r["overhead_ms"] for r in rows], 0.95)}
            for key, rows in groups.items()}


@app.get("/v1/log")
def read_log(limit: int = 50) -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text().splitlines()[-limit:]
    return [json.loads(line) for line in lines]


@app.get("/v1/events")
async def events() -> StreamingResponse:
    queue: asyncio.Queue[str] = asyncio.Queue()
    _subscribers.add(queue)

    async def stream():  # type: ignore[no-untyped-def]
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/")
def ui() -> FileResponse:
    return FileResponse(Path(__file__).parent / "ui" / "index.html")
