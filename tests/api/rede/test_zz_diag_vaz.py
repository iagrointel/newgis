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


def _pedir(sessao, metodo, caminho, alvo):
    url = _url_para(caminho, alvo)
    corpo = _corpo_para(metodo, caminho)
    if corpo and "__bruto__" in corpo:
        return sessao.request(metodo, url, content=corpo["__bruto__"],
                              headers={"Content-Type": "application/json"})
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
    fantasma = {"rede_id": str(U.uuid4()), "no_id": str(U.uuid4())}
    linhas = []
    for metodo, caminho in _rotas_de_rede_utilidades():
        if (metodo, caminho) in SEM_ALVO:
            continue
        r = _pedir(sessao_a, metodo, caminho, alvo)
        f = _pedir(sessao_a, metodo, caminho, fantasma)
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
