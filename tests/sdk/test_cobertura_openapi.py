"""Cláusula 2 do portão: "cobertura do SDK sobre o OpenAPI = 100% das rotas (teste compara)".

`operationId` de cada rota do `docs/openapi.json` é, por construção do `openapi-python-client`,
o nome do módulo gerado em `plat_gerado/api/**/<operationId>.py` — testa isso, não confia nisso:
para cada operação do OpenAPI, o módulo tem de existir e expor as funções padrão do gerado
(`sync_detailed`/`asyncio_detailed`, as duas que sempre existem — ver FUNCOES_PADRAO)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from openapi_python_client.strings import PythonIdentifier

RAIZ = Path(__file__).resolve().parents[2]
OPENAPI = RAIZ / "docs" / "openapi.json"
PLAT_GERADO_SRC = RAIZ / "sdk" / "python" / "src" / "plat_gerado"
VERBOS_HTTP = {"get", "post", "put", "patch", "delete"}
# `sync`/`asyncio` (a forma "desembrulhada") só existem quando o gerador consegue resolver um tipo de
# retorno concreto; rotas com resposta `Any`/sem schema (ex. /saude, /api/versao, /api/logout) só têm
# as duas "_detailed" — são as que a camada ergonômica usa sempre (ver plat/cliente.py), por isso são
# as únicas que valem como "cobertura": exigir as 4 reprovaria rota real por limite documentado do
# gerador, não por rota faltando.
FUNCOES_PADRAO = ("sync_detailed", "asyncio_detailed")


def _nome_do_modulo(operation_id: str) -> str:
    """O MESMO `PythonIdentifier(data.operationId, prefix=...)` que
    `openapi_python_client.parser.openapi.Endpoint.from_data` usa para nomear o módulo — não uma
    reimplementação por conta própria (que erraria justamente onde `{id}` no caminho gera `__` no
    `operationId` e o `PythonIdentifier` colapsa para `_`)."""
    return PythonIdentifier(operation_id, prefix="field_")


def _operacoes() -> list[tuple[str, str, str, str]]:
    """[(metodo, caminho, operation_id, nome_do_modulo), ...] das 196 rotas do OpenAPI comitado."""
    doc = json.loads(OPENAPI.read_text(encoding="utf-8"))
    operacoes = []
    for caminho, metodos in doc["paths"].items():
        for metodo, operacao in metodos.items():
            if metodo not in VERBOS_HTTP:
                continue
            assert "operationId" in operacao, f"{metodo.upper()} {caminho} sem operationId"
            oid = operacao["operationId"]
            operacoes.append((metodo, caminho, oid, _nome_do_modulo(oid)))
    return operacoes


def _achar_modulo(nome_modulo: str) -> Path | None:
    achados = list(PLAT_GERADO_SRC.glob(f"api/*/{nome_modulo}.py"))
    return achados[0] if achados else None


def test_toda_operacao_do_openapi_tem_modulo_gerado():
    operacoes = _operacoes()
    assert len(operacoes) >= 100, "poucas rotas encontradas — o OpenAPI comitado está certo?"
    faltando = [(m, c, oid) for m, c, oid, nm in operacoes if _achar_modulo(nm) is None]
    assert not faltando, f"{len(faltando)} rota(s) do OpenAPI sem módulo gerado: {faltando[:10]}"


def test_todo_modulo_gerado_expoe_as_quatro_funcoes_padrao():
    operacoes = _operacoes()
    sem_funcao = []
    for _, _, oid, nome_modulo_arquivo in operacoes:
        caminho = _achar_modulo(nome_modulo_arquivo)
        pacote = caminho.relative_to(RAIZ / "sdk" / "python" / "src").parent
        nome_modulo_python = ".".join((*pacote.parts, nome_modulo_arquivo))
        modulo = importlib.import_module(nome_modulo_python)
        faltando = [f for f in FUNCOES_PADRAO if not hasattr(modulo, f)]
        if faltando:
            sem_funcao.append((oid, faltando))
    assert not sem_funcao, f"módulo(s) sem função padrão: {sem_funcao[:10]}"


def test_contagem_de_modulos_gerados_bate_com_a_contagem_de_operacoes():
    """Nem um a mais (rota fantasma de uma geração anterior) nem um a menos."""
    esperados = {nm for _, _, _, nm in _operacoes()}
    modulos_gerados = {p.stem for p in PLAT_GERADO_SRC.glob("api/*/*.py") if p.stem != "__init__"}
    assert esperados == modulos_gerados, (
        f"só no OpenAPI: {esperados - modulos_gerados}; só no gerado: {modulos_gerados - esperados}"
    )
