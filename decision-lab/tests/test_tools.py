"""Travas do adaptador de ferramentas: lista permitida, validação, confirmação e extração de parâmetros.

  .venv/bin/python -m pytest tests -q        (ou: .venv/bin/python tests/test_tools.py)

Não usa modelo nem rede: o seletor é o de regras e o contexto escreve num diretório temporário.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab.actions import ActionEngine, ActionPolicy, Planner  # noqa: E402
from lab.executors import Home  # noqa: E402
from lab.tools import ToolNotAllowed  # noqa: E402
from lab.tools.builtin import ToolContext, build_registry, extract_device, extract_volume, parse_duration  # noqa: E402

DECISIONS = {"ignore", "home_control", "media", "timer_alarm", "knowledge", "complex"}


def make_engine(ttl: float = 60.0) -> ActionEngine:
    registry = build_registry()
    events: list[dict] = []
    ctx = ToolContext(home=Home(), notes_path=Path(tempfile.mkdtemp()) / "notes.jsonl", publish=events.append)
    engine = ActionEngine(registry, Planner(registry, "rules"), ctx, DECISIONS, llm=lambda text, large, rid: None,
                          policy=ActionPolicy(confirm_ttl=ttl))
    engine.events = events  # type: ignore[attr-defined]
    return engine


def act(engine: ActionEngine, text: str, decision: str, route: str, client: str = "c1") -> dict:
    return engine.act(text, decision, route, client, "rec")


# ------------------------------------------------------------------ lista permitida e validação
def test_registry_is_a_closed_list() -> None:
    registry = build_registry()
    assert "info.time" in registry.names
    for forbidden in ("shell.run", "os.system", "file.delete", "http.get", ""):
        try:
            registry.get(forbidden)
            raise AssertionError(f"{forbidden!r} não deveria existir")
        except ToolNotAllowed:
            pass
    assert not any("shell" in n or "exec" in n or "run" in n for n in registry.names)


def test_validation_rejects_bad_parameters() -> None:
    registry = build_registry()
    timer, device = registry.get("timer.create"), registry.get("home.set_device")
    assert timer.validate({"seconds": 600}) == []
    assert timer.validate({}) != []                                   # faltou a duração
    assert timer.validate({"seconds": 0}) != []                       # abaixo do mínimo
    assert timer.validate({"seconds": 10**9}) != []                   # acima de 24 h
    assert timer.validate({"seconds": "600"}) != []                   # tipo errado
    assert timer.validate({"seconds": True}) != []                    # bool não é inteiro
    assert timer.validate({"seconds": 60, "cmd": "rm -rf /"}) != []   # parâmetro fora do esquema
    assert device.validate({"device": "luz", "rooms": ["sala"], "state": "on"}) == []
    assert device.validate({"device": "cofre", "rooms": ["sala"], "state": "on"}) != []
    assert device.validate({"device": "luz", "rooms": ["sala; rm -rf"], "state": "on"}) != []
    assert device.validate({"device": "luz", "rooms": [], "state": "on"}) != []
    assert registry.get("note.add").validate({"text": "x" * 500}) != []
    assert registry.get("media.set_volume").validate({}) != []        # nem nível nem direção
    assert registry.get("media.set_volume").validate({"level": 11}) != []


def test_every_tool_has_a_route_and_each_route_has_a_default() -> None:
    registry = build_registry()
    for route in ("HOME_AUTOMATION", "MEDIA", "TIMERS", "LLM", "LLM_LARGE"):
        assert registry.for_route(route), route
        assert registry.default_for(route) is not None, route


# ------------------------------------------------------------------ extração de parâmetros
def test_parse_duration() -> None:
    cases = {"Alexa, timer de 10 minutos": 600, "bota um timer de uma hora e meia": 5400, "meia hora": 1800,
             "timer de 45 segundos": 45, "me avisa em vinte e cinco minutos": 1500, "um minuto e trinta segundos": 90,
             "cronômetro de 2 horas": 7200, "timer de macarrão, oito minutos": 480, "um minuto e meio": 90,
             "me lembra às 10h de ligar pro João": None, "me lembra de comprar pão": None}
    for text, expected in cases.items():
        assert parse_duration(text) == expected, (text, parse_duration(text), expected)


def test_extract_device_and_volume() -> None:
    assert extract_device("Alexa, acende a luz da sala") == {"device": "luz", "rooms": ["sala"], "state": "on"}
    assert extract_device("apaga todas as luzes") == {"device": "luz", "rooms": ["*"], "state": "off"}
    assert extract_device("desliga o ventilador do quarto")["state"] == "off"
    assert extract_device("destranca a porta da frente") == {"device": "porta", "rooms": ["frente"], "state": "on"}
    assert extract_device("tranca a porta") ["state"] == "off"
    assert extract_device("fecha o portão da garagem") == {"device": "portao", "rooms": ["garagem"], "state": "off"}
    assert extract_device("a luz da sala") ["state"] is None
    assert extract_volume("volume 7") == {"level": 7}
    assert extract_volume("aumenta o volume") == {"change": "up"}
    assert extract_volume("deixa no mudo") == {"level": 0}


# ------------------------------------------------------------------ fluxo
def test_ignored_and_invalid_decisions_never_run_a_tool() -> None:
    engine = make_engine()
    assert act(engine, "Você viu o jogo ontem?", "ignore", "NONE")["status"] == "ignored"
    assert act(engine, "acende a luz", "hack_the_planet", "HOME_AUTOMATION")["status"] == "rejected"
    assert act(engine, "acende a luz", "home_control", "ROTA_INEXISTENTE")["status"] == "rejected"
    assert engine.ctx.home.devices == {}


def test_safe_tools_run_and_report() -> None:
    engine = make_engine()
    out = act(engine, "Alexa, acende a luz da sala", "home_control", "HOME_AUTOMATION")
    assert (out["status"], out["name"], out["real"]) == ("executed", "home.set_device", False)
    assert engine.ctx.home.devices == {"luz:sala": "on"}
    assert act(engine, "Alexa, que horas são?", "knowledge", "LLM")["name"] == "info.time"
    assert act(engine, "Alexa, que dia é hoje?", "knowledge", "LLM")["name"] == "info.date"
    status = act(engine, "Alexa, como está o uso de CPU do computador?", "knowledge", "LLM")
    assert status["name"] == "info.system_status" and status["result"]["ram_total_gb"] > 0
    assert act(engine, "Alexa, qual a capital da França?", "knowledge", "LLM")["status"] == "answering"
    note = act(engine, "Alexa, me lembra de comprar pão", "timer_alarm", "TIMERS")
    assert (note["name"], note["args"]["text"]) == ("note.add", "comprar pão")
    assert engine.ctx.notes_path.exists()
    assert "comprar pão" in act(engine, "Alexa, quais são meus lembretes?", "timer_alarm", "TIMERS")["say"]


def test_missing_parameters_do_not_execute() -> None:
    engine = make_engine()
    out = act(engine, "Alexa, a luz", "home_control", "HOME_AUTOMATION")
    assert out["status"] == "needs_info" and out["errors"]
    assert engine.ctx.home.devices == {}


def test_real_timer_fires_an_event() -> None:
    engine = make_engine()
    out = act(engine, "Alexa, timer de 1 segundo", "timer_alarm", "TIMERS")
    assert (out["status"], out["name"], out["args"]["seconds"]) == ("executed", "timer.create", 1)
    assert len(act(engine, "quanto tempo falta?", "timer_alarm", "TIMERS")["result"]["timers"]) == 1
    time.sleep(1.4)
    assert any(e.get("type") == "timer_fired" for e in engine.events)  # type: ignore[attr-defined]
    assert act(engine, "quanto tempo falta?", "timer_alarm", "TIMERS")["result"]["timers"] == []


def test_sensitive_tools_need_confirmation() -> None:
    engine = make_engine()
    act(engine, "Alexa, me lembra de comprar pão", "timer_alarm", "TIMERS")
    out = act(engine, "Alexa, apaga todas as minhas anotações", "timer_alarm", "TIMERS")
    assert out["status"] == "needs_confirmation" and out["name"] == "note.clear"
    assert engine.ctx.notes_path.exists()                               # nada foi apagado ainda
    token = out["confirm"]["token"]
    assert engine.confirm(token, True, "outro-aparelho", "r")["status"] == "rejected"   # outro cliente não confirma
    assert engine.ctx.notes_path.exists()
    assert engine.confirm(token, True, "c1", "r")["status"] == "executed"
    assert not engine.ctx.notes_path.exists()
    assert engine.confirm(token, True, "c1", "r")["status"] == "rejected"               # token é de uso único


def test_confirmation_can_be_refused_spoken_and_expires() -> None:
    engine = make_engine()
    door = act(engine, "Alexa, abre a porta da frente", "home_control", "HOME_AUTOMATION")
    assert door["status"] == "needs_confirmation" and engine.ctx.home.devices == {}
    assert engine.spoken_confirmation("que horas são", "c1", "r") is None               # não é sim nem não
    assert engine.spoken_confirmation("sim", "c2", "r") is None                         # outro cliente
    assert engine.spoken_confirmation("Alexa, cancela", "c1", "r")["status"] == "cancelled"
    assert engine.ctx.home.devices == {}
    act(engine, "Alexa, abre a porta da frente", "home_control", "HOME_AUTOMATION")
    assert engine.spoken_confirmation("Sim!", "c1", "r")["status"] == "executed"
    assert engine.ctx.home.devices == {"porta:frente": "on"}
    assert act(engine, "Alexa, tranca a porta da frente", "home_control", "HOME_AUTOMATION")["status"] == "executed"  # fechar não é sensível

    for reply, expected in {"não, deixa": "cancelled", "Não, obrigado.": "cancelled", "deixa pra lá": "cancelled", "melhor não": "cancelled",
                            "pode sim": "executed", "sim, por favor": "executed", "Confirma!": "executed"}.items():
        engine = make_engine()
        act(engine, "Alexa, cancela todos os timers", "timer_alarm", "TIMERS")
        got = engine.spoken_confirmation(reply, "c1", "r")
        assert got is not None and got["status"] == expected, (reply, got)
    for unrelated in ("Alexa, que horas são?", "não sei se vai chover", "sim senhor capitão, vamos zarpar", "para de tocar"):
        engine = make_engine()
        act(engine, "Alexa, cancela todos os timers", "timer_alarm", "TIMERS")
        assert engine.spoken_confirmation(unrelated, "c1", "r") is None, unrelated

    quick = make_engine(ttl=0.2)
    token = act(quick, "Alexa, cancela todos os timers", "timer_alarm", "TIMERS")["confirm"]["token"]
    time.sleep(0.3)
    assert quick.confirm(token, True, "c1", "r")["status"] == "expired"


# ------------------------------------------------------------------ música (player de mentira, biblioteca de verdade)
def music_engine() -> ActionEngine:
    from lab.tools.player import Library, NullPlayer

    folder = Path(tempfile.mkdtemp())
    for name in ("Linkin Park/Crawling (live).mp3", "Djavan/Oceano.mp3", "Djavan/Flor de Lis.mp3", "Cover/faixa 1.wav", "notas.txt"):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    engine = make_engine()
    engine.ctx.player, engine.ctx.library, engine.ctx.registry = NullPlayer(), Library([folder]), engine.registry
    return engine


def test_music_query_extraction() -> None:
    from lab.tools.builtin import extract_music_query

    cases = {"Alexa, toca uma música do Djavan": {"query": "Djavan"}, "toca Linkin Park": {"query": "Linkin Park"},
             "bota Flor de Lis pra tocar": {"query": "Flor de Lis pra tocar"}, "Alexa, toca uma música": {},
             "toca qualquer coisa": {}, "coloca uma música aleatória": {}, "toca algo": {}, "continua a música": {},
             "quero ouvir Oceano": {"query": "Oceano"}, "toca": {}}
    for text, expected in cases.items():
        assert extract_music_query(text) == expected, (text, extract_music_query(text), expected)


def test_music_play_finds_asks_or_picks() -> None:
    engine = music_engine()
    hit = act(engine, "Alexa, toca Oceano do Djavan", "media", "MEDIA")
    assert (hit["name"], hit["status"], hit["result"]["title"]) == ("media.play", "executed", "Oceano"), hit
    assert "Oceano" in hit["say"] and "simulado" in hit["say"]          # NullPlayer: a resposta admite que não tocou
    assert engine.ctx.home.media["playing"] == "Oceano"
    artist = act(engine, "toca Djavan", "media", "MEDIA")
    assert artist["status"] == "executed" and artist["result"]["title"] in ("Oceano", "Flor de Lis")
    random_pick = act(engine, "Alexa, toca uma música", "media", "MEDIA")
    assert random_pick["status"] == "executed" and random_pick["result"]["random"] is True
    assert "escolhi" in random_pick["say"]
    miss = act(engine, "Alexa, toca Roberto Carlos", "media", "MEDIA")      # não existe: pergunta, não finge
    assert miss["status"] == "needs_info" and "Roberto Carlos" in miss["say"] and "Oceano" in miss["say"] + " ".join(engine.ctx.library.titles(9))
    assert engine.ctx.player.current.title != "Roberto Carlos"


def test_music_pause_resume_volume_status() -> None:
    engine = music_engine()
    assert "nada tocando" in act(engine, "pausa a música", "media", "MEDIA")["say"]
    act(engine, "toca Oceano", "media", "MEDIA")
    assert "pausada" in act(engine, "pausa a música", "media", "MEDIA")["say"]
    assert engine.ctx.player.paused and engine.ctx.home.media["playing"] is None
    resumed = act(engine, "continua a música", "media", "MEDIA")
    assert resumed["result"]["action"] == "resumed" and not engine.ctx.player.paused
    assert act(engine, "volume 3", "media", "MEDIA")["result"]["volume"] == 3
    assert act(engine, "aumenta o volume", "media", "MEDIA")["result"]["volume"] == 5
    assert act(engine, "volume 99", "media", "MEDIA")["status"] == "needs_info"      # fora da faixa: não executa
    assert "Oceano" in act(engine, "o que está tocando?", "media", "MEDIA")["say"]


def test_unsupported_request_says_so_instead_of_pretending() -> None:
    engine = music_engine()
    # o seletor por regras não escolhe a sentinela; ela é escolhida pelo modelo. Aqui testamos o motor diretamente.
    tool = engine.registry.get("system.cannot_do")
    out = engine._run(tool, {}, "manda um e-mail pro meu chefe", "rec")
    assert out["status"] == "unsupported" and "ainda não sei fazer" in out["say"] and "e-mail" in out["say"]
    assert engine.ctx.home.devices == {}


def test_unsupported_rule_replaces_silence_but_not_questions_or_neighbours() -> None:
    engine = music_engine()
    for text in ("Alexa, manda um e-mail pro meu chefe", "Alexa, pede uma pizza", "Alexa, abre o YouTube", "Alexa, liga pra minha mãe",
                 "Alexa, toca Djavan no Spotify", "Alexa, liga o aspirador robô", "Alexa, posta uma foto no Instagram"):
        for decision, route in (("complex", "LLM_LARGE"), ("media", "MEDIA"), ("home_control", "HOME_AUTOMATION"), ("ignore", "NONE")):
            out = act(engine, text, decision, route)
            assert out["status"] == "unsupported" and out["name"] == "system.cannot_do", (text, route, out["status"], out["name"])
            assert "ainda não sei fazer" in out["say"]
    # perguntas e pedidos que existem NÃO viram "não sei fazer"
    for text, decision, route in (("Alexa, como faço pra mandar um e-mail com anexo?", "knowledge", "LLM"),
                                  ("Alexa, quem inventou o telefone?", "knowledge", "LLM"),
                                  ("Alexa, toca Djavan", "media", "MEDIA"), ("Alexa, acende a luz da sala", "home_control", "HOME_AUTOMATION"),
                                  ("Alexa, timer de 5 minutos", "timer_alarm", "TIMERS")):
        assert act(engine, text, decision, route)["status"] != "unsupported", text
    # lembrete que MENCIONA uma ação sem ferramenta continua sendo só uma anotação
    for text in ("Alexa, me lembra de ligar pro dentista", "Alexa, não me deixa esquecer de pagar o boleto",
                 "Alexa, anota aí: mandar e-mail pro chefe"):
        note = act(engine, text, "timer_alarm", "TIMERS")
        assert (note["name"], note["status"]) == ("note.add", "executed"), (text, note["name"], note["status"])
    # não chamado pelo nome + roteador disse "ignorar": segue ignorado (nada de responder a conversa alheia)
    for text in ("Pedi uma pizza ontem e demorou", "Alexandre, manda um e-mail pro chefe", "Fala pra ela abrir o YouTube",
                 "A Alexa da minha tia não liga pra nada"):
        assert act(engine, text, "ignore", "NONE")["status"] == "ignored", text


def test_help_lists_real_simulated_and_missing() -> None:
    engine = music_engine()
    out = act(engine, "o que você sabe fazer?", "knowledge", "LLM")
    assert out["name"] == "system.help" and out["status"] == "executed", out
    assert "media.play" in out["result"]["real"] and "home.set_device" in out["result"]["simulated"]
    assert "enviar e-mail" in out["say"] and "SIMULADO" in out["say"] or "simulado" in out["say"]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except Exception as error:  # noqa: BLE001
                failed += 1
                print(f"FALHA {name}: {error!r}")
    sys.exit(1 if failed else 0)
