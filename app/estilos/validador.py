"""Validação do documento de estilo na gravação (item L2-02-a-modelo-estilo).

Chamado depois de `tipos.validar('estilo', dados)` nas duas rotas de `app/catalogo/rotas_itens.py` que
gravam `dados` (mesmo padrão de `app/catalogo/documento.py::validar_grafo`). Tudo aqui é o que JSON
Schema puro não expressa: (1) o `plat_construtor` compila sem erro (campo ausente, faixa invertida,
tipo desconhecido — `app/estilos/compilador.py`); (2) todo campo citado em `maplibre.layers` (o que o
cliente ENVIOU, antes de qualquer reescrita) está no vocabulário `plat_construtor.campos`; (3) o
documento enviado é uma Style Spec v8 válida pelo pacote oficial `@maplibre/maplibre-gl-style-spec`
(`ferramentas/estilo/validar.mjs`, versão fixada em `ferramentas/estilo/package.json`).

Depois de validar o que foi ENVIADO, `validar_estilo` REESCREVE `dados['corpo']['maplibre']` com o
resultado de `compilador.compilar(plat_construtor)` — a forma canônica. Isto é o que garante a cláusula
de ida-e-volta sem perda (gravar, ler, gravar de novo dá o mesmo documento byte a byte, exceto os
metadados do item) e a invariante do L2-01 (mapa e legenda nascem da mesma função): nunca existe um
`maplibre` gravado que não seja exatamente o que aquele `plat_construtor` implica. O cliente pode
enviar um `maplibre` provisório (o editor manda o que compilou no navegador) — ele só precisa ser
válido; o que fica gravado é sempre recompilado no servidor, a única fonte de verdade.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.erros import ErroAPI
from app.estilos import compilador

RAIZ = Path(__file__).resolve().parents[2]
VALIDADOR_JS = RAIZ / "ferramentas" / "estilo" / "validar.mjs"
NODE_TIMEOUT_S = 10

# fonte injetada para o validador oficial conseguir checar `source-layer`/`source` sem que o documento
# grave uma URL real (C2 do L2_CONCEITO: a fonte é ligada na renderização, nunca no documento). O
# documento gravado NUNCA tem `source`/`source-layer` por camada (são ligados na renderização); o
# validador precisa deles para aceitar a Style Spec, então esta função os injeta só para validar.
_FONTE_VETOR = "camada"
_FONTE_RASTER = "camada_raster"
_FONTE_FICTICIA = {
    _FONTE_VETOR: {"type": "vector", "tiles": ["https://exemplo.invalido/{z}/{x}/{y}"]},
    _FONTE_RASTER: {"type": "raster", "tiles": ["https://exemplo.invalido/{z}/{x}/{y}.png"], "tileSize": 256},
}


def _layers_com_fonte(layers: list[dict]) -> list[dict]:
    saida = []
    for layer in layers:
        layer = dict(layer)
        if layer.get("type") == "raster":
            layer["source"] = _FONTE_RASTER
        else:
            layer.setdefault("source", _FONTE_VETOR)
            layer.setdefault("source-layer", _FONTE_VETOR)
        saida.append(layer)
    return saida


def _expressoes_get(no) -> list[str]:
    """Percorre um valor de `paint`/`layout`/`filter` e devolve todo campo citado por `["get", campo]`,
    `["has", campo]` ou `["in", campo, ...]` — as três formas que uma expressão MapLibre lê um atributo."""
    achados: list[str] = []
    if isinstance(no, list):
        if len(no) >= 2 and no[0] in ("get", "has") and isinstance(no[1], str):
            achados.append(no[1])
        elif len(no) >= 2 and no[0] == "in" and isinstance(no[1], str):
            achados.append(no[1])
        for item in no:
            achados.extend(_expressoes_get(item))
    elif isinstance(no, dict):
        for v in no.values():
            achados.extend(_expressoes_get(v))
    return achados


def _campos_citados(maplibre: dict) -> list[str]:
    achados: list[str] = []
    for layer in maplibre.get("layers") or []:
        for chave in ("paint", "layout", "filter"):
            if chave in layer:
                achados.extend(_expressoes_get(layer[chave]))
    return achados


def _checar_campos(maplibre: dict, pc: dict) -> None:
    campos = set(pc.get("campos") or [])
    if not campos:
        return  # sem vocabulário declarado: a compilação já barra campo fora de "campos" quando há lista
    for campo in _campos_citados(maplibre):
        if campo not in campos:
            raise ErroAPI(
                422,
                "campo_inexistente",
                f"a expressão do estilo referencia o campo {campo!r}, fora de plat_construtor.campos",
                {"campo": campo},
            )


def _chamar_style_spec(maplibre: dict) -> None:
    documento = {"version": 8, "sources": _FONTE_FICTICIA, "layers": _layers_com_fonte(maplibre.get("layers") or [])}
    if maplibre.get("sprite"):
        documento["sprite"] = maplibre["sprite"]
    if maplibre.get("glyphs"):
        documento["glyphs"] = maplibre["glyphs"]
    try:
        r = subprocess.run(
            ["node", str(VALIDADOR_JS)],
            input=json.dumps(documento),
            capture_output=True,
            text=True,
            timeout=NODE_TIMEOUT_S,
            cwd=str(VALIDADOR_JS.parent),
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ErroAPI(503, "validador_indisponivel", f"validador da Style Spec indisponível: {e}") from e
    if r.returncode == 2:
        raise ErroAPI(
            422, "estilo_invalido", "documento de estilo malformado para o validador oficial",
            {"stderr": r.stderr.strip()},
        )
    if r.returncode != 0:
        raise ErroAPI(
            503, "validador_indisponivel",
            f"validador da Style Spec saiu com código {r.returncode}: {r.stderr.strip()}",
        )
    try:
        resultado = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise ErroAPI(503, "validador_indisponivel", "saída do validador não é JSON") from e
    if not resultado.get("ok"):
        erros = resultado.get("erros") or [{"mensagem": "estilo inválido"}]
        raise ErroAPI(
            422,
            "estilo_invalido",
            f"estilo inválido contra a MapLibre Style Spec: {erros[0]['mensagem']}",
            {"erros": erros},
        )


def validar_estilo(tipo: str, dados: dict) -> None:
    if tipo != "estilo":
        return
    corpo = dados.get("corpo") or {}
    pc = corpo.get("plat_construtor")
    maplibre = corpo.get("maplibre")
    if not isinstance(pc, dict) or not isinstance(maplibre, dict):
        return  # tipos.validar (JSON Schema) já reprova ausência/tipo errado dos dois campos obrigatórios

    _checar_campos(maplibre, pc)
    _chamar_style_spec(maplibre)

    try:
        compilado = compilador.compilar(pc)
    except compilador.EstiloInvalido as e:
        raise ErroAPI(422, "plat_construtor_invalido", str(e), {"campo": e.campo}) from e

    # forma canônica: o que fica gravado é sempre o resultado da compilação, nunca o que o cliente mandou
    # (garante a ida-e-volta sem perda e a invariante mapa=legenda; ver docstring do módulo).
    corpo["maplibre"] = compilado
