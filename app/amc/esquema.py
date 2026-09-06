"""Esquema do modelo (docs/esquemas/amc_modelo.v1.json) e hash canônico (decisão A1 do L3L6_CONCEITO).

`versao_hash` = sha256 do JSON canônico: `json.dumps(definicao, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` em UTF-8. É a ÚNICA forma; scripts/amc_hash_independente.py recomputa a mesma coisa sem importar
este módulo e o teste confere que dá igual ao gravado. Validação em duas camadas: JSON Schema (Draft 2020-12,
jsonschema) e regras semânticas que o esquema não expressa (id único, soma de pesos > 0, percentual fecha 100).
Toda violação sai como 422 `modelo_invalido` com a lista `violacoes[{clausula, caminho, mensagem}]`."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[2]
CAMINHO_ESQUEMA = ROOT / "docs" / "esquemas" / "amc_modelo.v1.json"
ESQUEMA_NOME = "amc_modelo.v1"
TOLERANCIA_PERCENTUAL = 0.01


@lru_cache(maxsize=1)
def esquema() -> dict:
    return json.loads(CAMINHO_ESQUEMA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validador() -> Draft202012Validator:
    s = esquema()
    Draft202012Validator.check_schema(s)
    return Draft202012Validator(s, format_checker=Draft202012Validator.FORMAT_CHECKER)


def canonico(definicao) -> bytes:
    """JSON canônico do documento (chaves ordenadas, sem espaço, UTF-8). NaN/Infinity são recusados (não são JSON)."""
    return json.dumps(definicao, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )


def hash_modelo(definicao) -> str:
    return hashlib.sha256(canonico(definicao)).hexdigest()


# ---------------------------------------------------------------- tradução dos erros do jsonschema
_TRADUCAO = {
    "required": lambda e: f"campo obrigatório ausente: {', '.join(sorted(set(e.validator_value) - set(e.instance)))}"
    if isinstance(e.instance, dict) else "campo obrigatório ausente",
    "minimum": lambda e: f"{e.instance!r} é menor que o mínimo {e.validator_value}",
    "maximum": lambda e: f"{e.instance!r} é maior que o máximo {e.validator_value}",
    "enum": lambda e: f"{e.instance!r} não está entre os valores admitidos {list(e.validator_value)}",
    "const": lambda e: f"{e.instance!r} difere do valor exigido {e.validator_value!r}",
    "type": lambda e: f"tipo errado: esperado {e.validator_value}, veio {type(e.instance).__name__}",
    "additionalProperties": lambda e: "campo não previsto no esquema: "
    + ", ".join(sorted(k for k in e.instance if k not in (e.schema.get("properties") or {})))
    if isinstance(e.instance, dict) else "campo não previsto no esquema",
    "pattern": lambda e: f"{e.instance!r} não segue o padrão {e.validator_value}",
    "minLength": lambda e: f"texto mais curto que {e.validator_value} caracteres",
    "maxLength": lambda e: f"texto mais longo que {e.validator_value} caracteres",
    "minItems": lambda e: f"lista com menos de {e.validator_value} elementos",
    "maxItems": lambda e: f"lista com mais de {e.validator_value} elementos",
    "minProperties": lambda e: f"objeto com menos de {e.validator_value} campos",
}


def _caminho(e) -> str:
    return e.json_path


def _clausula(e) -> str:
    if e.validator == "required" and isinstance(e.instance, dict):
        faltando = sorted(set(e.validator_value) - set(e.instance))
        return f"{e.json_path}.{faltando[0] if faltando else '?'}: obrigatório"
    return f"{e.json_path}: {e.validator} {json.dumps(e.validator_value, ensure_ascii=False)}"


def _violacao_schema(e) -> dict:
    traduzir = _TRADUCAO.get(e.validator)
    return {"clausula": _clausula(e), "caminho": _caminho(e), "mensagem": traduzir(e) if traduzir else e.message}


def _violacoes_semanticas(definicao: dict) -> list[dict]:
    """O que o JSON Schema não diz: id único entre fatores e restrições, soma dos pesos > 0, percentual fecha 100."""
    v: list[dict] = []
    fatores = definicao.get("fatores") or []
    if not isinstance(fatores, list):
        return v
    vistos: dict[str, int] = {}
    soma = 0.0
    for i, f in enumerate(fatores):
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        if isinstance(fid, str):
            if fid in vistos:
                v.append({"clausula": "fatores[].id único", "caminho": f"$.fatores[{i}].id",
                          "mensagem": f"fator duplicado: '{fid}' já aparece em $.fatores[{vistos[fid]}]"})
            else:
                vistos[fid] = i
        peso = f.get("peso")
        if isinstance(peso, (int, float)) and not isinstance(peso, bool):
            if peso < 0:
                v.append({"clausula": "fatores[].peso >= 0", "caminho": f"$.fatores[{i}].peso",
                          "mensagem": f"peso negativo: {peso}"})
            else:
                soma += float(peso)
        if "transformacao" not in f:
            v.append({"clausula": "fatores[].transformacao obrigatória", "caminho": f"$.fatores[{i}].transformacao",
                      "mensagem": f"fator '{fid}' sem transformação (valor bruto → favorabilidade)"})
    if fatores and all(isinstance(f, dict) for f in fatores) and soma <= 0:
        v.append({"clausula": "soma(fatores[].peso) > 0", "caminho": "$.fatores",
                  "mensagem": f"soma dos pesos é {soma:g}: nenhum fator pesa"})
    comb = (definicao.get("combinador") or {}).get("tipo") if isinstance(definicao.get("combinador"), dict) else None
    if comb == "percentual" and abs(soma - 100.0) > TOLERANCIA_PERCENTUAL:
        v.append({"clausula": "combinador percentual: soma(fatores[].peso) = 100", "caminho": "$.fatores",
                  "mensagem": f"no combinador 'percentual' os pesos fecham 100; somam {soma:g}"})
    restricoes = definicao.get("restricoes") or []
    if isinstance(restricoes, list):
        vistos_r: dict[str, int] = {}
        for i, r in enumerate(restricoes):
            rid = r.get("id") if isinstance(r, dict) else None
            if not isinstance(rid, str):
                continue
            if rid in vistos_r or rid in vistos:
                v.append({"clausula": "restricoes[].id único e distinto de fatores[].id",
                          "caminho": f"$.restricoes[{i}].id", "mensagem": f"identificador repetido: '{rid}'"})
            vistos_r[rid] = i
    return v


def violacoes(definicao) -> list[dict]:
    """Todas as violações (esquema + semântica), na ordem do documento. Lista vazia = válido."""
    if not isinstance(definicao, dict):
        return [{"clausula": "$: type object", "caminho": "$", "mensagem": "a definição precisa ser um objeto JSON"}]
    erros = sorted(_validador().iter_errors(definicao), key=lambda e: (list(e.absolute_path), e.validator))
    lista = [_violacao_schema(e) for e in erros]
    lista.extend(_violacoes_semanticas(definicao))
    return lista


def validar(definicao) -> dict:
    """Devolve a definição validada (a mesma) ou levanta 422 modelo_invalido com todas as violações."""
    lista = violacoes(definicao)
    if lista:
        raise ErroAPI(422, "modelo_invalido", f"modelo inválido: {lista[0]['clausula']} — {lista[0]['mensagem']}",
                      {"violacoes": lista, "esquema": ESQUEMA_NOME})
    try:
        canonico(definicao)
    except ValueError as e:  # NaN/Infinity
        raise ErroAPI(422, "modelo_invalido", f"modelo inválido: número não representável em JSON ({e})",
                      {"violacoes": [{"clausula": "números finitos", "caminho": "$", "mensagem": str(e)}]}) from e
    return definicao


def validar_pesos(definicao: dict, pesos: dict | None) -> dict:
    """Pesos de uma execução: chaves = ids de fator do modelo, ≥ 0, soma > 0 (percentual fecha 100). Sem pesos =
    os do modelo. Devolve {id: float} completo (fator ausente no pedido recebe o peso do modelo)."""
    fatores = {f["id"]: float(f["peso"]) for f in definicao["fatores"]}
    if pesos is None:
        pesos = {}
    if not isinstance(pesos, dict):
        raise ErroAPI(422, "pesos_invalidos", "pesos precisam ser um objeto {fator: peso}")
    desconhecidos = sorted(set(pesos) - set(fatores))
    if desconhecidos:
        raise ErroAPI(422, "pesos_invalidos", f"fator inexistente no modelo: {', '.join(desconhecidos)}",
                      {"desconhecidos": desconhecidos, "fatores": sorted(fatores)})
    finais = dict(fatores)
    for k, w in pesos.items():
        if isinstance(w, bool) or not isinstance(w, (int, float)) or w != w:
            raise ErroAPI(422, "pesos_invalidos", f"peso de '{k}' não é número", {"fator": k})
        if w < 0:
            raise ErroAPI(422, "pesos_invalidos", f"peso negativo em '{k}': {w}", {"fator": k, "peso": w})
        finais[k] = float(w)
    soma = sum(finais.values())
    if soma <= 0:
        raise ErroAPI(422, "pesos_invalidos", "soma dos pesos é zero: nenhum fator pesa", {"pesos": finais})
    comb = (definicao.get("combinador") or {}).get("tipo", "soma_ponderada_normalizada")
    if comb == "percentual" and abs(soma - 100.0) > TOLERANCIA_PERCENTUAL:
        raise ErroAPI(422, "pesos_invalidos", f"no combinador 'percentual' os pesos fecham 100; somam {soma:g}",
                      {"pesos": finais, "soma": soma})
    return finais
