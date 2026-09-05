"""Configuração do plat: lê o .env da raiz, valida as chaves obrigatórias e expõe `settings`
(dataclass congelada). Falha na partida nomeando a chave ausente ou inválida (ADR 0001 seção 8).
`settings` é carregado na primeira leitura (módulo __getattr__), para que testes de unidade
consigam importar este módulo sem .env."""

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
AMBIENTES = ("producao", "dev")
NIVEIS = ("DEBUG", "INFO", "WARNING", "ERROR")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class ErroConfiguracao(RuntimeError):
    """Chave de configuração ausente ou inválida; a mensagem nomeia a chave."""


@dataclass(frozen=True)
class Settings:
    PLAT_DSN: str
    PLAT_SECRET: str
    PLAT_AMBIENTE: str
    PLAT_URL_PUBLICA: str
    PLAT_GIT_SHA: str | None
    PLAT_MARTIN_URL: str | None
    PLAT_TITILER_URL: str | None
    PLAT_GARAGE_URL: str | None
    PLAT_LOG_NIVEL: str

    @property
    def producao(self) -> bool:
        return self.PLAT_AMBIENTE == "producao"

    def servicos(self) -> dict[str, str | None]:
        return {"martin": self.PLAT_MARTIN_URL, "titiler": self.PLAT_TITILER_URL, "garage": self.PLAT_GARAGE_URL}


def _obrigatoria(valores: Mapping[str, str | None], chave: str) -> str:
    v = (valores.get(chave) or "").strip()
    if not v:
        raise ErroConfiguracao(f"chave obrigatória ausente: {chave}")
    return v


def _opcional(valores: Mapping[str, str | None], chave: str) -> str | None:
    v = (valores.get(chave) or "").strip()
    return v or None


def carregar(valores: Mapping[str, str | None]) -> Settings:
    """Monta e valida um Settings a partir de um dicionário (o .env, o ambiente ou um teste)."""
    dsn = _obrigatoria(valores, "PLAT_DSN")
    if not dsn.startswith("postgresql://"):
        raise ErroConfiguracao("PLAT_DSN inválida: deve começar com postgresql://")
    segredo = _obrigatoria(valores, "PLAT_SECRET")
    if not _HEX64.match(segredo):
        raise ErroConfiguracao("PLAT_SECRET inválido: exige 64 caracteres hexadecimais (openssl rand -hex 32)")
    ambiente = _obrigatoria(valores, "PLAT_AMBIENTE")
    if ambiente not in AMBIENTES:
        raise ErroConfiguracao(f"PLAT_AMBIENTE inválido: {ambiente!r}; admitidos {AMBIENTES}")
    url = _obrigatoria(valores, "PLAT_URL_PUBLICA").rstrip("/")
    if not url.startswith("https://"):
        raise ErroConfiguracao("PLAT_URL_PUBLICA inválida: deve começar com https://")
    nivel = (_opcional(valores, "PLAT_LOG_NIVEL") or "INFO").upper()
    if nivel not in NIVEIS:
        raise ErroConfiguracao(f"PLAT_LOG_NIVEL inválido: {nivel!r}; admitidos {NIVEIS}")
    if ambiente == "producao" and nivel == "DEBUG":
        logging.getLogger("plat.settings").warning("PLAT_LOG_NIVEL=DEBUG não vale em producao; rebaixado para INFO")
        nivel = "INFO"
    return Settings(
        PLAT_DSN=dsn,
        PLAT_SECRET=segredo,
        PLAT_AMBIENTE=ambiente,
        PLAT_URL_PUBLICA=url,
        PLAT_GIT_SHA=_opcional(valores, "PLAT_GIT_SHA"),
        PLAT_MARTIN_URL=_opcional(valores, "PLAT_MARTIN_URL"),
        PLAT_TITILER_URL=_opcional(valores, "PLAT_TITILER_URL"),
        PLAT_GARAGE_URL=_opcional(valores, "PLAT_GARAGE_URL"),
        PLAT_LOG_NIVEL=nivel,
    )


def valores_do_ambiente() -> dict[str, str | None]:
    """.env da raiz, com o ambiente do processo por cima (o ambiente vence, como no SIG de teste interno)."""
    valores: dict[str, str | None] = dict(dotenv_values(ROOT / ".env"))
    for chave in Settings.__dataclass_fields__:
        if chave in os.environ:
            valores[chave] = os.environ[chave]
    return valores


@lru_cache(maxsize=1)
def obter() -> Settings:
    return carregar(valores_do_ambiente())


def __getattr__(nome: str):
    if nome == "settings":
        return obter()
    raise AttributeError(nome)
