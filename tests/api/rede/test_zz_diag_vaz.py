"""Sonda de diagnostico (temporaria) do item L4-23: mede, rota a rota de /api/rede, (a) o status da
tentativa cruzada, (b) o que da resposta e dado de B fora do membro `instance` da RFC 9457, e (c) se a
resposta para o id REAL de B se distingue da resposta para um id que nao existe em lugar nenhum
(oraculo de existencia = canal lateral). Nao asserta nada: imprime a tabela."""
import json as J
import re
import uuid as U

import pytest

from tests.api.rede.test_isolamento_por_inquilino import (
    SEM_ALVO, _corpo_para, _rotas_de_rede_utilidades, _url_para, rede_b_com_topologia,  # noqa: F401
)

RE_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _min_do_esquema(esq, comps, prof=0):
    """Menor corpo que satisfaz o esquema declarado: so os `required`, cada um com o `default`/primeiro
    `enum`/minimo do tipo. Serve para tirar o 422 de esquema da frente e deixar a rota chegar ao ponto
    onde decide sobre o recurso de OUTRO inquilino."""
    if prof > 6 or not isinstance(esq, dict):
        return None
    if "$ref" in esq:
        return _min_do_esquema(comps.get(esq["$ref"].rsplit("/", 1)[-1], {}), comps, prof + 1)
    for chave in ("anyOf", "oneOf", "allOf"):
        if chave in esq:
            for alt in esq[chave]:
                if not (isinstance(alt, dict) and alt.get("type") == "null"):
                    return _min_do_esquema(alt, comps, prof + 1)
    if "default" in esq:
        return esq["default"]
    if "enum" in esq and esq["enum"]:
        return esq["enum"][0]
    t = esq.get("type")
    if t == "object" or "properties" in esq:
        props = esq.get("properties", {})
        return {n: _min_do_esquema(props.get(n, {}), comps, prof + 1) for n in esq.get("required", [])}
    if t == "array":
        n = int(esq.get("minItems", 0))
        return [_min_do_esquema(esq.get("items", {}), comps, prof + 1) for _ in range(n)]
    if t == "integer":
        return max(int(esq.get("minimum", 1)), 1)
    if t == "number":
        return float(max(esq.get("minimum", 1), 1))
    if t == "boolean":
        return False
    if t == "string":
        if esq.get("format") == "uuid":
            return str(U.uuid4())
        return "x" * max(int(esq.get("minLength", 1)), 1)
    return None


def _esquema_app():
    from app.main import app
    return app.openapi()


def _corpo_do_esquema(metodo, caminho, esquema):
    op = esquema["paths"].get(caminho, {}).get(metodo.lower(), {})
    rb = op.get("requestBody") or {}
    esq = (rb.get("content") or {}).get("application/json", {}).get("schema")
    if not esq:
        return None
    return _min_do_esquema(esq, esquema.get("components", {}).get("schemas", {}))


def _pedir(sessao, metodo, caminho, alvo, corpo_extra=None):
    url = _url_para(caminho, alvo)
    corpo = _corpo_para(metodo, caminho)
    if corpo and "__bruto__" in corpo:
        return sessao.request(metodo, url, content=corpo["__bruto__"],
                              headers={"Content-Type": "application/json"})
    if corpo is None and corpo_extra is not None:
        corpo = corpo_extra
    return sessao.request(metodo, url, json=corpo)


def _normal(texto):
    """Corpo sem `instance` (eco do caminho pedido), sem req_id e com todo uuid mascarado — o que sobra e
    o que a resposta REALMENTE conta sobre o recurso."""
    try:
        d = J.loads(texto)
    except Exception:
        return RE_UUID.sub("<uuid>", texto)
    if isinstance(d, dict):
        d.pop("instance", None)
        d.pop("req_id", None)
    return RE_UUID.sub("<uuid>", J.dumps(d, sort_keys=True))


def test_diag(sessao_a, rede_b_com_topologia):
    alvo = rede_b_com_topologia
    esquema = _esquema_app()
    fantasma = {"rede_id": str(U.uuid4()), "no_id": str(U.uuid4())}
    linhas = []
    for metodo, caminho in _rotas_de_rede_utilidades():
        if (metodo, caminho) in SEM_ALVO:
            continue
        gerado = _corpo_do_esquema(metodo, caminho, esquema)
        r = _pedir(sessao_a, metodo, caminho, alvo)
        if r.status_code == 422 and gerado is not None:
            r2 = _pedir(sessao_a, metodo, caminho, alvo, gerado)
            if r2.status_code != 422:
                r = r2
        f = _pedir(sessao_a, metodo, caminho, fantasma, gerado)
        marcas = []
        resto = _normal(r.text)
        if alvo["rede_id"] in resto or alvo["no_id"] in resto:
            marcas.append("UUID_DE_B")
        if "l423-alvo-b" in resto:
            marcas.append("NOME_DE_B")
        if alvo["rede_id"] in r.text and "UUID_DE_B" not in marcas:
            marcas.append("so_instance")
        oraculo = "" if (r.status_code == f.status_code and resto == _normal(f.text)) else \
            f"ORACULO({r.status_code}/{f.status_code})"
        linhas.append(f"{r.status_code:>3} {metodo:<7}{caminho:<55} {','.join(marcas) or '-':<22}{oraculo}")
    print("\n===DIAG===")
    print("\n".join(linhas))
    print("===FIM===")
