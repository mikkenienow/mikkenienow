"""Servidor do laboratório: API de decisão + roteamento + log + eventos em tempo real + UI.

  uvicorn lab.server:app --port 8000      (ou: scripts/lab.sh)

POST /v1/decide  {"input": "...", "options": [...]|{...}?, "question": "..."?, "backend": "..."?}
POST /v1/route   {"input": "...", "backend"?, "min_confidence"?, "low_confidence"?, "execute"?: true}
GET  /v1/backends | /v1/state | /v1/log?limit= | /v1/stats | /v1/events (SSE) | /  (UI)
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from lab import backends as registry
from lab.backends.base import Backend
from lab.executors import Home, LlmExecutor
from lab.router import LLM_ROUTES, Policy, route_decision
from lab.taxonomy import ROOT, Taxonomy
from lab.types import normalize_options

CONFIG = registry.load_config()
TAXONOMY = Taxonomy.load()
LOG_PATH = ROOT / "runs" / "decisions.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Decision Lab", version="0.1.0")
_backends: dict[str, Backend] = {}
_backend_lock = threading.Lock()
_home = Home()
_stats: dict[str, Any] = {"decisions": 0, "routes": {}, "llm_calls": 0, "llm_calls_avoided": 0,
                          "decision_ms_total": 0.0, "llm_ms_total": 0.0}
_subscribers: set[asyncio.Queue[str]] = set()
_loop: asyncio.AbstractEventLoop | None = None
_started = time.time()


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
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "default_backend": CONFIG["default_backend"], "loaded": sorted(_backends)}


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


@app.get("/v1/state")
def state() -> dict[str, Any]:
    return _home.snapshot()


@app.get("/v1/stats")
def stats() -> dict[str, Any]:
    n = max(1, _stats["decisions"])
    return {**_stats, "mean_decision_ms": round(_stats["decision_ms_total"] / n, 1),
            "mean_llm_ms": round(_stats["llm_ms_total"] / max(1, _stats["llm_calls"]), 1)}


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
