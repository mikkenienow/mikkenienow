"""Adaptador de ferramentas: o que o assistente PODE fazer, separado de quem decide.

O modelo de decisão nunca executa nada. Ele só escolhe (a) a intenção e (b) uma ferramenta desta lista
fechada. Cada ferramenta declara os parâmetros que aceita; nada fora do esquema passa, e não existe
ferramenta de "rodar comando". O fluxo completo está em lab/actions.py:

    entrada -> roteador -> validação da decisão -> ferramenta (desta lista) -> resultado -> log
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Param:
    type: str  # str | int | enum | enum_list
    required: bool = True
    choices: tuple[str, ...] = ()
    min: int | None = None
    max: int | None = None
    max_len: int = 200
    description: str = ""


@dataclass
class Tool:
    name: str
    route: str                      # rota da taxonomia em que a ferramenta pode ser escolhida
    description_pt: str
    description_en: str             # o que o modelo de decisão lê ao escolher a ferramenta
    handler: Callable[[dict[str, Any], Any], dict[str, Any]]
    extract: Callable[[str], dict[str, Any]]            # fala -> parâmetros (regras determinísticas)
    say: Callable[[dict[str, Any], dict[str, Any]], str]  # (args, resultado) -> frase curta para a pessoa
    params: dict[str, Param] = field(default_factory=dict)
    real: bool = False              # True: efeito real no PC; False: estado simulado
    # True, ou função(args) -> bool quando só algumas combinações são sensíveis (ex.: destrancar a porta)
    sensitive: bool | Callable[[dict[str, Any]], bool] = False
    confirm_text: Callable[[dict[str, Any]], str] | None = None
    check: Callable[[dict[str, Any]], str | None] | None = None  # regra entre parâmetros (ex.: "um ou outro")
    kind: str = "tool"              # "unsupported": ferramenta-sentinela "isso eu não sei fazer"
    examples: tuple[str, ...] = ()  # frases de exemplo (para a tela "o que eu posso pedir")
    effect: str = ""                # o que ela faz de verdade, em uma frase
    keywords: str = ""              # regex (texto normalizado) usada pelo seletor por regras
    default: bool = False           # ferramenta padrão da rota quando nenhuma regra casa

    def is_sensitive(self, args: dict[str, Any]) -> bool:
        return self.sensitive(args) if callable(self.sensitive) else bool(self.sensitive)

    def validate(self, args: dict[str, Any]) -> list[str]:
        """Erros de validação (lista vazia = ok). Parâmetro desconhecido também é erro."""
        errors = [f"parâmetro desconhecido: {k}" for k in args if k not in self.params]
        for name, p in self.params.items():
            if name not in args or args[name] is None:
                if p.required:
                    errors.append(f"faltou {p.description or name}")
                continue
            v = args[name]
            if p.type == "int":
                if isinstance(v, bool) or not isinstance(v, int):
                    errors.append(f"{name}: esperado inteiro")
                elif (p.min is not None and v < p.min) or (p.max is not None and v > p.max):
                    errors.append(f"{name}: fora do intervalo {p.min}..{p.max}")
            elif p.type == "str":
                if not isinstance(v, str) or not v.strip():
                    errors.append(f"{name}: esperado texto")
                elif len(v) > p.max_len:
                    errors.append(f"{name}: texto longo demais (máx. {p.max_len})")
            elif p.type == "enum":
                if v not in p.choices:
                    errors.append(f"{name}: valor não permitido ({v!r})")
            elif p.type == "enum_list":
                if not isinstance(v, list) or not v or any(x not in p.choices for x in v):
                    errors.append(f"{name}: lista com valor não permitido ({v!r})")
            else:
                errors.append(f"{name}: tipo de parâmetro desconhecido no esquema ({p.type})")
        if not errors and self.check and (problem := self.check(args)):
            errors.append(problem)
        return errors

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "route": self.route, "description": self.description_pt, "real": self.real,
                "kind": self.kind, "examples": list(self.examples), "effect": self.effect,
                "sensitive": "depende dos parâmetros" if callable(self.sensitive) else bool(self.sensitive),
                "params": {k: {"type": p.type, "required": p.required, **({"choices": list(p.choices)} if p.choices else {}),
                               **({"min": p.min, "max": p.max} if p.type == "int" else {})}
                           for k, p in self.params.items()}}


class ToolNotAllowed(KeyError):
    pass


class NeedsInfo(Exception):
    """A ferramenta entendeu o pedido mas falta algo (ou não achou); a mensagem é a pergunta para a pessoa."""


class ToolRegistry:
    """Lista explícita de ferramentas permitidas. O que não está aqui não existe para o assistente."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}
        if len(self._tools) != len(tools):
            raise ValueError("nome de ferramenta duplicado")

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolNotAllowed(name)
        return self._tools[name]

    def for_route(self, route: str) -> list[Tool]:
        return [t for t in self._tools.values() if t.route == route]

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def default_for(self, route: str) -> Tool | None:
        return next((t for t in self.for_route(route) if t.default), None)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> list[dict[str, Any]]:
        return [t.describe() for t in self._tools.values()]
