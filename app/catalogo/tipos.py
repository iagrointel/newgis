"""Registro de tipos de item (ADR 0004 seção 3): cache de plat.tipo_item (recarregado a cada 60 s) e validação do
campo `dados` pelo JSON Schema do tipo (Draft 2020-12, jsonschema). Erro vira 422 dados_invalidos com o caminho do
campo; tipo inexistente vira 422 tipo_inexistente."""

import threading
import time

from jsonschema import Draft202012Validator

from app import db
from app.erros import ErroAPI

VALIDADE_CACHE_S = 60.0
_cache: dict[str, dict] = {}
_validadores: dict[str, Draft202012Validator] = {}
_carregado_em = 0.0
_trava = threading.Lock()


def _carregar() -> None:
    global _carregado_em
    with db.db() as cur:
        cur.execute(
            "SELECT nome, familia, rotulo, descricao, esquema, esquema_versao, icone, modulo_front, abre_em, "
            "tem_dado_fisico, linha_dona FROM plat.tipo_item ORDER BY nome"
        )
        linhas = cur.fetchall()
    novos = {}
    validadores = {}
    for r in linhas:
        t = dict(r)
        t["abre_em"] = list(t["abre_em"] or [])
        novos[t["nome"]] = t
        validadores[t["nome"]] = Draft202012Validator(t["esquema"], format_checker=Draft202012Validator.FORMAT_CHECKER)
    _cache.clear()
    _cache.update(novos)
    _validadores.clear()
    _validadores.update(validadores)
    _carregado_em = time.monotonic()


def todos(forcar: bool = False) -> dict[str, dict]:
    if forcar or not _cache or time.monotonic() - _carregado_em > VALIDADE_CACHE_S:
        with _trava:
            if forcar or not _cache or time.monotonic() - _carregado_em > VALIDADE_CACHE_S:
                _carregar()
    return _cache


def obter(nome: str) -> dict:
    t = todos().get(nome)
    if t is None:
        raise ErroAPI(422, "tipo_inexistente", f"tipo de item inexistente: {nome}", {"tipo": nome})
    return t


def familia_de(nome: str) -> str:
    return obter(nome)["familia"]


def erros_de(nome: str, dados) -> list[dict]:
    """Lista [{campo, erro, regra}] (vazia = válido). Caminho absoluto do validador, unido por '.'."""
    obter(nome)
    v = _validadores[nome]
    saida = []
    for e in sorted(v.iter_errors(dados), key=lambda e: list(e.absolute_path)):
        caminho = ".".join(str(p) for p in e.absolute_path)
        saida.append({"campo": caminho or "(raiz)", "erro": e.message[:500], "regra": e.validator})
    return saida


def validar(nome: str, dados) -> dict:
    if not isinstance(dados, dict):
        raise ErroAPI(
            422,
            "dados_invalidos",
            "o campo dados precisa ser um objeto JSON",
            [{"campo": "(raiz)", "erro": "não é objeto", "regra": "type"}],
        )
    erros = erros_de(nome, dados)
    if erros:
        raise ErroAPI(422, "dados_invalidos", f"dados fora do esquema do tipo {nome}", erros)
    return dados
