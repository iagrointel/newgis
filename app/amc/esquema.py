"""Validação em duas camadas do documento do modelo AMC (item L3-01-a-modelo-dado; ADR/CONCEITO A1/A4).

Camada 1 (`erros_estruturais`): JSON Schema Draft 2020-12 publicado em `docs/esquemas/amc_modelo.v1.json`
— tipos, campos obrigatórios, enums, faixas de valor por item isolado. Camada 2 (`erros_semanticos`): o que
o JSON Schema não expressa porque olha o array INTEIRO (soma de pesos, id repetido) ou a COERÊNCIA interna de
uma transformação (faixa invertida, faixa degenerada, notas × quebras fora de conta) — cada erro carrega a
`clausula` (texto fixo, é o que a rota devolve em `detalhe` no 422).

Hash: `hash_canonico` reaproveita `app.catalogo.documento.sha256_canonico` (mesma forma canônica —
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(',',':'))` — já usada pelo item L5-05; um único
jeito de canonicalizar no produto inteiro). `scripts/amc_hash_independente.py` reimplementa a mesma fórmula
BYTE A BYTE, sem importar este módulo, para o adversário recomputar por fora."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from app.catalogo.documento import sha256_canonico

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_ESQUEMA = RAIZ / "docs" / "esquemas" / "amc_modelo.v1.json"


@lru_cache(maxsize=1)
def esquema() -> dict:
    return json.loads(ARQUIVO_ESQUEMA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validador() -> Draft202012Validator:
    return Draft202012Validator(esquema(), format_checker=Draft202012Validator.FORMAT_CHECKER)


def hash_canonico(definicao: dict) -> str:
    return sha256_canonico(definicao)


def erros_estruturais(definicao) -> list[dict]:
    """Camada 1: JSON Schema. Caminho absoluto do validador, unido por '.'; vazio = estrutura válida."""
    if not isinstance(definicao, dict):
        return [{"campo": "(raiz)", "erro": "o modelo precisa ser um objeto JSON", "clausula": "definicao objeto"}]
    saida = []
    for e in sorted(_validador().iter_errors(definicao), key=lambda e: list(e.absolute_path)):
        caminho = ".".join(str(p) for p in e.absolute_path)
        saida.append({"campo": caminho or "(raiz)", "erro": e.message[:500], "clausula": _clausula_schema(e)})
    return saida


def _clausula_schema(e) -> str:
    caminho = list(e.absolute_path)
    # fatores/<n>/peso, fatores/<n> (obrigatoriedade), etc. — nomeia a cláusula do jeito que o portão exige
    if len(caminho) >= 2 and caminho[0] == "fatores" and caminho[-1] == "peso":
        return "fatores[].peso >= 0"
    if (len(caminho) == 2 and caminho[0] == "fatores" and e.validator == "required"
            and "transformacao" in str(e.message)):
        return "fatores[].transformacao obrigatória"
    if len(caminho) >= 1 and caminho[0] == "fatores":
        return f"fatores[].{caminho[-1] if len(caminho) > 1 else '(objeto)'}: {e.validator}"
    return f"{'/'.join(str(c) for c in caminho) or '(raiz)'}: {e.validator}"


def erros_semanticos(definicao: dict) -> list[dict]:
    """Camada 2: cruza itens do array (nunca expressável em JSON Schema puro). Só roda depois de a estrutura
    já estar OK o bastante para existir `fatores` como lista de objetos — chame depois de `erros_estruturais`
    não ter erro em `fatores[n].peso`/`fatores[n].transformacao`/`fatores[n].id`, senão os erros se repetem."""
    saida = []
    fatores = definicao.get("fatores") if isinstance(definicao, dict) else None
    if not isinstance(fatores, list):
        return saida

    ids_vistos: dict[str, int] = {}
    soma_pesos = 0.0
    soma_valida = True
    for i, f in enumerate(fatores):
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        if isinstance(fid, str):
            if fid in ids_vistos:
                saida.append({
                    "campo": f"fatores.{i}.id", "erro": f"id '{fid}' repetido (já usado em fatores.{ids_vistos[fid]})",
                    "clausula": "fatores[].id único",
                })
            else:
                ids_vistos[fid] = i
        peso = f.get("peso")
        if isinstance(peso, (int, float)) and not isinstance(peso, bool):
            if not math.isfinite(peso):
                saida.append({
                    "campo": f"fatores.{i}.peso", "erro": f"peso não é um número finito ({peso!r})",
                    "clausula": "fatores[].peso >= 0",
                })
                soma_valida = False
            else:
                soma_pesos += peso
        else:
            soma_valida = False
        transformacao = f.get("transformacao")
        if isinstance(transformacao, dict):
            saida.extend(_erros_transformacao(i, transformacao))

    if soma_valida and fatores and soma_pesos <= 0:
        saida.append({
            "campo": "fatores", "erro": f"soma dos pesos é {soma_pesos:g}, precisa ser > 0",
            "clausula": "soma(fatores[].peso) > 0",
        })

    restricoes = definicao.get("restricoes") if isinstance(definicao, dict) else None
    if isinstance(restricoes, list):
        vistos_r: dict[str, int] = {}
        for i, r in enumerate(restricoes):
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if isinstance(rid, str):
                if rid in vistos_r:
                    saida.append({
                        "campo": f"restricoes.{i}.id", "erro": f"id '{rid}' repetido",
                        "clausula": "restricoes[].id único",
                    })
                else:
                    vistos_r[rid] = i
    return saida


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _erros_transformacao(i: int, t: dict) -> list[dict]:
    """Coerência INTERNA da transformação (fila de conserto §2 do adversário do rascunho anterior: faixa
    invertida, faixa degenerada, notas×quebras fora de conta, degraus fora de ordem, gaussiana sem parâmetro
    utilizável). Isto é o que evita que um documento entre no banco, ganhe hash e só quebre quando o item
    L3-01-d tentar executá-lo."""
    tipo = t.get("tipo")
    base = f"fatores.{i}.transformacao"
    erros = []
    if tipo == "linear":
        mn, mx = _num(t.get("minimo")), _num(t.get("maximo"))
        if mn is not None and mx is not None and mn >= mx:
            erros.append({
                "campo": f"{base}.minimo/maximo", "erro": f"minimo ({mn:g}) precisa ser < maximo ({mx:g})",
                "clausula": "transformacao.linear: minimo < maximo",
            })
    elif tipo == "potencia":
        mn, mx = _num(t.get("minimo")), _num(t.get("maximo"))
        if mn is not None and mx is not None and mn >= mx:
            erros.append({
                "campo": f"{base}.minimo/maximo", "erro": f"minimo ({mn:g}) precisa ser < maximo ({mx:g})",
                "clausula": "transformacao.potencia: minimo < maximo",
            })
    elif tipo == "faixas":
        quebras = t.get("quebras")
        notas = t.get("notas")
        if isinstance(quebras, list) and all(_num(q) is not None for q in quebras):
            if list(quebras) != sorted(quebras):
                erros.append({
                    "campo": f"{base}.quebras", "erro": f"quebras fora de ordem crescente: {quebras}",
                    "clausula": "transformacao.faixas: quebras em ordem crescente",
                })
            if len(set(quebras)) != len(quebras):
                erros.append({
                    "campo": f"{base}.quebras", "erro": "quebras repetidas criam faixa de largura zero",
                    "clausula": "transformacao.faixas: quebras sem repetição",
                })
        if isinstance(quebras, list) and isinstance(notas, list) and len(notas) != len(quebras) + 1:
            erros.append({
                "campo": f"{base}.notas",
                "erro": f"{len(notas)} notas para {len(quebras)} quebras (esperado {len(quebras) + 1})",
                "clausula": "transformacao.faixas: len(notas) == len(quebras) + 1",
            })
    elif tipo == "degraus":
        bandas = t.get("bandas")
        if isinstance(bandas, list) and len(bandas) > 1:
            ates = [_num(b.get("ate")) for b in bandas if isinstance(b, dict)]
            if all(a is not None for a in ates) and ates != sorted(ates):
                erros.append({
                    "campo": f"{base}.bandas", "erro": f"bandas fora de ordem crescente de 'ate': {ates}",
                    "clausula": "transformacao.degraus: bandas em ordem crescente de ate",
                })
    elif tipo == "gaussiana":
        desvio = _num(t.get("desvio"))
        if desvio is not None and desvio <= 0:
            erros.append({
                "campo": f"{base}.desvio", "erro": f"desvio ({desvio:g}) precisa ser > 0",
                "clausula": "transformacao.gaussiana: desvio > 0",
            })
    return erros
