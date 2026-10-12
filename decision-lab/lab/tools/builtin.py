"""As ferramentas permitidas nesta PoC, e só elas.

Reais (efeito de verdade no PC):  info.time, info.date, info.system_status, timer.* (dispara um evento na UI),
                                   note.* (arquivo runs/notes.jsonl)
Simuladas (estado em memória):     home.set_device, media.*
Encaminhadas ao LLM local:         llm.answer, llm.answer_large

Sensíveis (pedem confirmação):     timer.cancel_all, note.clear, home.set_device quando abre/destranca porta ou portão
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from lab.executors import Home
from lab.tools import Param, Tool, ToolRegistry


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


@dataclass
class ToolContext:
    """Tudo em que uma ferramenta pode tocar. Não há acesso a shell, rede ou arquivos fora de notes_path."""
    home: Home
    notes_path: Path
    publish: Callable[[dict[str, Any]], None] = lambda event: None
    log: Callable[[dict[str, Any]], None] = lambda record: None
    timers: dict[str, threading.Timer] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


# ----------------------------------------------------------------------------- extração de parâmetros
WAKE = r"^\s*(o+|ei|hey|oi)?\s*,?\s*(alexa|alexia|alecsa)\s*[,.!?:]*\s*"
POLITE = r"\b(por favor|por gentileza|pra mim|para mim|ai)\b"

NUMBERS = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
           "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14,
           "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20, "trinta": 30,
           "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90}
_TENS = "vinte|trinta|quarenta|cinquenta|sessenta|setenta|oitenta|noventa"
_NUM = rf"(?:\d+|(?:{_TENS}) e (?:um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove)|{'|'.join(NUMBERS)})"
UNITS = {"segundo": 1, "seg": 1, "minuto": 60, "min": 60, "hora": 3600}
_UNIT = r"(segundos?|seg|minutos?|min|horas?)\b"   # sem "h": "às 10h" é horário, não duração


def parse_number(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    if " e " in token:
        a, b = token.split(" e ", 1)
        return NUMBERS[a] + NUMBERS[b] if a in NUMBERS and b in NUMBERS else None
    return NUMBERS.get(token)


def parse_duration(text: str) -> int | None:
    """Segundos pedidos na fala: "10 minutos", "uma hora e meia", "meia hora", "um minuto e trinta segundos"."""
    t = norm(text)
    total, found = 0, False
    for m in re.finditer(rf"\b({_NUM})\s*{_UNIT}", t):
        n = parse_number(m.group(1))
        if n is None:
            continue
        unit = UNITS[m.group(2) if m.group(2) in ("seg", "min") else m.group(2).rstrip("s")]
        total += n * unit
        found = True
        if re.match(r"\s*e mei[ao]\b", t[m.end():]):       # "uma hora e meia", "um minuto e meio"
            total += unit // 2
    if re.search(r"\bmeia hora\b", t):
        total, found = total + 1800, True
    if re.search(r"\bmeio minuto\b", t):
        total, found = total + 30, True
    return total if found else None


def strip_request(text: str, verbs: str) -> str:
    """Tira a wake word, o verbo do pedido e a cortesia; devolve o "conteúdo" (o que tocar, o que anotar)."""
    t = unicodedata.normalize("NFC", re.sub(WAKE, "", text.strip(), flags=re.I))
    # os verbos estão sem acento: casa no texto normalizado e corta o original no mesmo ponto
    # (em NFC cada letra acentuada vira uma letra só ao normalizar, então os índices coincidem)
    plain = norm(t)
    if len(plain) == len(t) and (m := re.match(rf"\s*({verbs})\b[\s,:]*", plain)):
        t = t[m.end():]
    t = re.sub(POLITE, "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" ,.!?:;")


DEVICES = {r"\bluz|lus\b|luiz|lampada|ilumina|abajur": "luz", r"\bar\b|ar.condicionado|aquecedor|clima": "clima",
           r"\btv\b|televis|\bteve\b": "tv", r"cortina|persiana": "cortina", r"portao": "portao",
           r"\bporta\b|tranca|fechadura": "porta", r"ventilador": "ventilador", r"cafeteira": "cafeteira",
           r"maquina": "maquina", r"tomada": "tomada"}
ROOMS = ("sala", "quarto", "cozinha", "banheiro", "varanda", "garagem", "escritorio", "corredor", "frente")
ON = r"\b(acend|lig|abr|ativ|destranc|destrav)"
OFF = r"\b(apag|deslig|fech|tranc|trav|desativ)"


def extract_device(text: str) -> dict[str, Any]:
    t = norm(text)
    device = next((d for pat, d in DEVICES.items() if re.search(pat, t)), None)
    rooms = [r for r in ROOMS if re.search(rf"\b{r}\b", t)]
    if re.search(r"\b(tudo|todas|todos|casa toda|casa inteira)\b", t):
        rooms = ["*"]
    state = "off" if re.search(OFF, t) else "on" if re.search(ON, t) else None
    if state is None and re.search(r"\bescuro\b", t):
        device, state = device or "luz", "on"
    return {"device": device, "rooms": rooms or ["sala"], "state": state}


def extract_volume(text: str) -> dict[str, Any]:
    t = norm(text)
    if m := re.search(rf"volume\s*(?:para|pra|em|no|n[oa]\s)?\s*({_NUM})\b", t):
        return {"level": parse_number(m.group(1))}
    if re.search(r"\b(mudo|silencia|sem som)\b", t):
        return {"level": 0}
    if re.search(r"\bmaximo\b", t):
        return {"level": 10}
    if re.search(r"aument|mais alto|sobe", t):
        return {"change": "up"}
    if re.search(r"abaix|diminu|mais baixo|baixa", t):
        return {"change": "down"}
    return {}


# ----------------------------------------------------------------------------- handlers
def _time(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    now = datetime.now().astimezone()
    return {"time": now.strftime("%H:%M"), "timezone": now.tzname()}


WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
          "novembro", "dezembro"]


def _date(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    now = datetime.now().astimezone()
    return {"date": now.strftime("%Y-%m-%d"), "weekday": WEEKDAYS[now.weekday()],
            "text": f"{WEEKDAYS[now.weekday()]}, {now.day} de {MONTHS[now.month - 1]} de {now.year}"}


def _system_status(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    import psutil
    mem, disk = psutil.virtual_memory(), psutil.disk_usage("/")
    return {"cpu_percent": psutil.cpu_percent(interval=0.2), "cpu_count": psutil.cpu_count(),
            "ram_used_gb": round((mem.total - mem.available) / 2**30, 1), "ram_total_gb": round(mem.total / 2**30, 1),
            "disk_free_gb": round(disk.free / 2**30), "disk_total_gb": round(disk.total / 2**30)}


def _set_device(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    with ctx.home.lock:
        for room in args["rooms"]:
            ctx.home.devices[f"{args['device']}:{room}"] = args["state"]
    return {"device": args["device"], "rooms": args["rooms"], "state": args["state"]}


def _media_play(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    with ctx.home.lock:
        ctx.home.media["playing"] = args["query"]
        return dict(ctx.home.media)


def _media_pause(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    with ctx.home.lock:
        ctx.home.media["playing"] = None
        return dict(ctx.home.media)


def _media_volume(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    with ctx.home.lock:
        if "level" in args:
            ctx.home.media["volume"] = args["level"]
        else:
            step = 2 if args["change"] == "up" else -2
            ctx.home.media["volume"] = max(0, min(10, ctx.home.media["volume"] + step))
        return dict(ctx.home.media)


def _timer_fire(timer_id: str, ctx: ToolContext) -> None:
    with ctx.home.lock:
        entry = next((t for t in ctx.home.timers if t.get("id") == timer_id), None)
        if entry is None or entry["status"] != "running":
            return
        entry["status"] = "fired"
    ctx.timers.pop(timer_id, None)
    event = {"type": "timer_fired", "ts": datetime.now().astimezone().isoformat(timespec="seconds"), "timer": entry}
    ctx.log(event)
    ctx.publish(event)
    ctx.publish({"type": "state", **ctx.home.snapshot()})


def _timer_create(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    timer_id = uuid.uuid4().hex[:8]
    entry = {"id": timer_id, "label": args.get("label") or "timer", "seconds": args["seconds"],
             "created": time.strftime("%H:%M:%S"), "due": time.strftime("%H:%M:%S", time.localtime(time.time() + args["seconds"])),
             "status": "running", "request": args.get("label") or "timer"}
    handle = threading.Timer(args["seconds"], _timer_fire, (timer_id, ctx))
    handle.daemon = True
    with ctx.home.lock:
        ctx.home.timers.append(entry)
        ctx.home.timers[:] = ctx.home.timers[-20:]
    ctx.timers[timer_id] = handle
    handle.start()
    return dict(entry)


def _timer_list(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    with ctx.home.lock:
        return {"timers": [dict(t) for t in ctx.home.timers if t.get("status") == "running"]}


def _timer_cancel_all(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    cancelled = 0
    with ctx.home.lock:
        for entry in ctx.home.timers:
            if entry.get("status") == "running":
                entry["status"] = "cancelled"
                cancelled += 1
    for handle in list(ctx.timers.values()):
        handle.cancel()
    ctx.timers.clear()
    return {"cancelled": cancelled}


def _notes(ctx: ToolContext) -> list[dict[str, Any]]:
    if not ctx.notes_path.exists():
        return []
    return [json.loads(line) for line in ctx.notes_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _note_add(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    note = {"id": uuid.uuid4().hex[:8], "ts": datetime.now().astimezone().isoformat(timespec="seconds"), "text": args["text"]}
    with ctx.lock:
        ctx.notes_path.parent.mkdir(parents=True, exist_ok=True)
        with ctx.notes_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
        return {"note": note, "total": len(_notes(ctx))}


def _note_list(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    with ctx.lock:
        return {"notes": _notes(ctx)[-10:]}


def _note_clear(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    with ctx.lock:
        removed = len(_notes(ctx))
        if ctx.notes_path.exists():
            ctx.notes_path.unlink()
        return {"removed": removed}


def _llm(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return {"forwarded": True}  # o motor de ações chama o LLM local de forma assíncrona (lab/actions.py)


# ----------------------------------------------------------------------------- frases de resposta
DEVICE_NAMES = {"luz": "a luz", "clima": "o ar", "tv": "a TV", "cortina": "a cortina", "porta": "a porta", "portao": "o portão",
                "ventilador": "o ventilador", "cafeteira": "a cafeteira", "maquina": "a máquina", "tomada": "a tomada"}
OPENABLE = ("porta", "portao", "cortina")


ROOM_NAMES = {"sala": "da sala", "quarto": "do quarto", "cozinha": "da cozinha", "banheiro": "do banheiro",
              "varanda": "da varanda", "garagem": "da garagem", "escritorio": "do escritório", "corredor": "do corredor",
              "frente": "da frente", "*": "da casa toda"}


def _where(rooms: list[str]) -> str:
    return " e ".join(ROOM_NAMES.get(r, r) for r in rooms)


def _say_device(args: dict[str, Any], result: dict[str, Any]) -> str:
    verb = (("Abri" if args["state"] == "on" else "Fechei") if args["device"] in OPENABLE
            else ("Liguei" if args["state"] == "on" else "Desliguei"))
    return f"{verb} {DEVICE_NAMES[args['device']]} {_where(args['rooms'])}".strip() + " (simulado: nenhum aparelho de verdade foi acionado)."


def human_duration(seconds: int) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    parts = [f"{h} h" if h else "", f"{m} min" if m else "", f"{s} s" if s else ""]
    return " ".join(p for p in parts if p) or "0 s"


def _say_timers(args: dict[str, Any], result: dict[str, Any]) -> str:
    timers = result["timers"]
    if not timers:
        return "Não há timers rodando."
    return "Timers rodando: " + "; ".join(f"{t['label']} até {t['due']}" for t in timers) + "."


def _say_notes(args: dict[str, Any], result: dict[str, Any]) -> str:
    notes = result["notes"]
    return "Você não tem anotações." if not notes else "Suas anotações: " + "; ".join(n["text"] for n in notes) + "."


# ----------------------------------------------------------------------------- a lista permitida
def _door_opening(args: dict[str, Any]) -> bool:
    return args.get("device") in ("porta", "portao") and args.get("state") == "on"


def build_registry() -> ToolRegistry:
    none: Callable[[str], dict[str, Any]] = lambda text: {}
    return ToolRegistry([
        # --- consultas locais (reais) ---
        Tool("info.time", "LLM", "Dizer a hora atual do PC", "Tell the current time of day (what time is it now)",
             _time, none, lambda a, r: f"São {r['time']}.", real=True,
             keywords=r"que horas|horas sao|que hora e|me diz a hora|me fala a hora|horario agora"),
        Tool("info.date", "LLM", "Dizer a data de hoje e o dia da semana",
             "Tell today's date or which day of the week it is today",
             _date, none, lambda a, r: f"Hoje é {r['text']}.", real=True,
             keywords=r"que dia e hoje|qual (e )?a data|data de hoje|dia da semana|que dia da semana|hoje e que dia|dia e hoje"),
        Tool("info.system_status", "LLM", "Estado do PC: uso de CPU, memória e disco",
             "Report this computer's own status: CPU usage, memory (RAM) in use, free disk space",
             _system_status, none,
             lambda a, r: (f"CPU em {r['cpu_percent']:.0f}%, memória {r['ram_used_gb']} de {r['ram_total_gb']} GB, "
                           f"{r['disk_free_gb']} GB livres em disco."), real=True,
             keywords=r"\b(cpu|processador|memoria ram|memoria livre|uso de memoria|espaco em disco|disco livre)\b"
                      r"|(como esta|status|estado|uso) d[oa] (pc|computador|maquina|servidor)"),
        Tool("llm.answer", "LLM", "Responder a pergunta com o LLM local",
             "Answer any other question or look up general knowledge (facts, weather, math, definitions, how-to)",
             _llm, none, lambda a, r: "Vou responder.", default=True),
        Tool("llm.answer_large", "LLM_LARGE", "Tarefa complexa: usar o LLM local maior",
             "Carry out a complex writing, planning, summarizing or comparison task",
             _llm, none, lambda a, r: "Vou pensar nisso.", default=True),

        # --- casa (simulada) ---
        Tool("home.set_device", "HOME_AUTOMATION", "Ligar/desligar (ou abrir/fechar) um dispositivo da casa simulada",
             "Turn a home device on or off, or open/close it",
             _set_device, extract_device, _say_device,
             params={"device": Param("enum", choices=tuple(DEVICE_NAMES), description="qual dispositivo"),
                     "rooms": Param("enum_list", choices=ROOMS + ("*",), description="o cômodo"),
                     "state": Param("enum", choices=("on", "off"), description="se é para ligar ou desligar")},
             sensitive=_door_opening,
             confirm_text=lambda a: f"Abrir {DEVICE_NAMES[a['device']]} {_where(a['rooms'])}?",
             keywords=rf"({ON[2:]}|{OFF[2:]}).*({'|'.join(DEVICES)})", default=True),

        # --- mídia (simulada) ---
        Tool("media.pause", "MEDIA", "Pausar a música", "Pause or stop whatever is playing",
             _media_pause, none, lambda a, r: "Pausa simulada: não há player de verdade.",
             keywords=r"\b(pausa|pausar|pause|para a musica|para o som|para de tocar|parar|stop)\b"),
        Tool("media.set_volume", "MEDIA", "Mudar o volume (0 a 10)", "Change the volume: louder, quieter, mute, or a level",
             _media_volume, extract_volume, lambda a, r: f"Volume simulado em {r['volume']}: nenhum som foi alterado.",
             params={"level": Param("int", required=False, min=0, max=10, description="o volume"),
                     "change": Param("enum", required=False, choices=("up", "down"))},
             check=lambda a: None if ("level" in a) != ("change" in a) else "faltou dizer o volume (um número, mais alto ou mais baixo)",
             keywords=r"volume|aument|abaix|diminu|mais alto|mais baixo|\bmudo\b|sem som|silencia"),
        Tool("media.play", "MEDIA", "Tocar música, rádio ou podcast", "Play music, a song, an artist, a radio or a podcast",
             _media_play, lambda text: {"query": strip_request(text, r"toca|tocar|toque|bota|coloca|poe|play|quero ouvir|ouvir|liga")[:120] or None},
             lambda a, r: f"Entendi: tocar “{a['query']}”. Ainda é simulado: nenhum som foi iniciado, não há player.",
             params={"query": Param("str", max_len=120, description="o que tocar")}, default=True),

        # --- timers (reais: disparam um evento na interface) ---
        Tool("timer.cancel_all", "TIMERS", "Cancelar todos os timers", "Cancel or stop the running timers or alarms",
             _timer_cancel_all, none, lambda a, r: f"Cancelei {r['cancelled']} timer(s).", real=True, sensitive=True,
             confirm_text=lambda a: "Cancelar todos os timers?",
             keywords=r"(cancel|remov|exclu|apag|desativ|desliga|para)\w* ((o|os|todos|meu|meus) )*(timer|timers|alarme|alarmes|cronometro|despertador)"),
        Tool("timer.list", "TIMERS", "Listar os timers em andamento", "Tell which timers are running or how much time is left",
             _timer_list, none, _say_timers, real=True,
             keywords=r"quanto (tempo )?falta|quais (sao )?(os )?(meus )?(timers|alarmes)|tem (algum )?(timer|alarme)|(timers|alarmes) (ativos|rodando)"),
        Tool("timer.create", "TIMERS", "Criar um timer com duração",
             "Start a countdown timer or alarm for a given duration (minutes, seconds, hours from now)",
             _timer_create, lambda text: {"seconds": parse_duration(text), "label": _timer_label(text)},
             lambda a, r: f"Timer de {human_duration(a['seconds'])} criado; toca às {r['due']}.", real=True,
             params={"seconds": Param("int", min=1, max=24 * 3600, description="a duração do timer"),
                     "label": Param("str", required=False, max_len=60)},
             keywords=rf"\b({_NUM})\s*{_UNIT}|meia hora|\btimer\b|cronometr|temporizador"),

        # --- anotações / lembretes sem horário (reais: arquivo runs/notes.jsonl) ---
        Tool("note.clear", "TIMERS", "Apagar todas as anotações", "Delete or erase all saved notes and reminders",
             _note_clear, none, lambda a, r: f"Apaguei {r['removed']} anotação(ões).", real=True, sensitive=True,
             confirm_text=lambda a: "Apagar todas as anotações?",
             keywords=r"(apag|limp|exclu|remov|delet)\w* ((todas|todos|as|os|minhas|meus) )*(anotac|notas|lembretes)"),
        Tool("note.list", "TIMERS", "Ler as anotações salvas", "Read back the saved notes or reminders",
             _note_list, none, _say_notes, real=True,
             keywords=r"(quais|le|leia|ler|mostra|lista|fala)\w* .{0,20}(anotac|notas|lembretes)|o que (eu )?(anotei|tenho anotado)|minhas (anotacoes|notas)|meus lembretes"),
        Tool("note.add", "TIMERS", "Guardar uma anotação ou lembrete (sem horário)",
             "Save a note or a reminder to do something (no countdown duration given)",
             _note_add, lambda text: {"text": strip_request(text, NOTE_VERBS)[:200] or None},
             lambda a, r: f"Anotei: {a['text']}.", real=True,
             params={"text": Param("str", max_len=200, description="o que anotar")},
             keywords=rf"^\s*(?:alexa\W+)?(?:{NOTE_VERBS})\b", default=True),
    ])


NOTE_VERBS = (r"me lembra de|me lembra|me lembre de|me lembre|lembra de|lembra|lembrete de|lembrete para|lembrete pra|lembrete|"
              r"anota ai que|anota ai|anota que|anota|anote|cria um lembrete de|cria um lembrete para|cria um lembrete pra|"
              r"cria um lembrete|adiciona um lembrete de|adiciona|nao me deixa esquecer de|nao deixa eu esquecer de")


def _timer_label(text: str) -> str | None:
    """"timer de macarrão, oito minutos" -> "macarrão" (opcional)."""
    t = re.sub(WAKE, "", text.strip(), flags=re.I)
    m = re.search(r"(?:timer|alarme|cron[oô]metro)\s+(?:de|do|da|para|pra|pro)\s+(?:o\s+|a\s+)?([^,.!?]+)", t, flags=re.I)
    if not m:
        return None
    label = re.split(r"\s+(?:de|em|por|para|pra|daqui a)\s+(?=\S+\s+(?:segundo|minuto|hora))", m.group(1), flags=re.I)[0].strip()
    if len(label) < 2 or parse_duration(label) is not None:
        return None
    return label[:60]
