"""Regressão do achado H3-L3-01 (adversário HARD-03, 08/09): peso/valor INFINITO era aceito pelos modelos
(allow_inf_nan padrão True; inf > 0 passa no gt=0) e propagava até `motor.executar`, violando o CHECK
`escala_resultado_nota_check` no INSERT — HTTP 500 em vez de 4xx. `allow_inf_nan=False` nos campos de entrada
recusa no pydantic (422) antes de qualquer trabalho de banco. NaN já era 422 (NaN>0 é falso)."""

from __future__ import annotations

import json
import secrets

P = "/api/multiescala"


def _area():
    x, y = -47.9, -15.8
    return {"type": "Polygon", "coordinates": [[[x, y], [x + 0.02, y], [x + 0.02, y + 0.02], [x, y + 0.02], [x, y]]]}


def _conjunto(s):
    r = s.post(f"{P}/conjuntos", json={"nome": f"zt{secrets.token_hex(3)}", "area": _area()})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _fator(s):
    r = s.post(f"{P}/fatores", json={"nome": f"zt{secrets.token_hex(3)}", "resolucao_fonte_m": 100.0,
                                     "papel": "atrai", "unidade": "un", "fonte": "t"})
    fid = r.json()["id"]
    s.post(f"{P}/fatores/{fid}/amostras",
           json={"amostras": [{"lon": -47.9 + 0.005 * i, "lat": -15.8 + 0.005 * i, "valor": 1.0} for i in range(4)]})
    return fid


def test_peso_infinito_recusado_com_422(sessao_a):
    cid = _conjunto(sessao_a)
    fid = _fator(sessao_a)
    try:
        corpo = ('{"resolucao_m":500.0,"fatores":[{"fator_id":"%s","peso":1e400}],'
                 '"aprovacao_tipo":"top_pct","aprovacao_valor":50}') % fid
        r = sessao_a.request("POST", f"{P}/conjuntos/{cid}/macro", content=corpo,
                             headers={"Content-Type": "application/json"})
        assert r.status_code == 422, (r.status_code, r.text[:200])
        # controle positivo: peso finito executa
        r = sessao_a.request("POST", f"{P}/conjuntos/{cid}/macro",
                             content=json.dumps({"resolucao_m": 500.0, "fatores": [{"fator_id": fid, "peso": 1.0}],
                                                 "aprovacao_tipo": "top_pct", "aprovacao_valor": 50}),
                             headers={"Content-Type": "application/json"})
        assert r.status_code == 201, r.text
    finally:
        sessao_a.delete(f"{P}/conjuntos/{cid}")


def test_amostra_valor_infinito_recusado_com_422(sessao_a):
    r = sessao_a.post(f"{P}/fatores", json={"nome": f"zt{secrets.token_hex(3)}", "resolucao_fonte_m": 100.0,
                                            "papel": "atrai", "unidade": "un", "fonte": "t"})
    fid = r.json()["id"]
    ra = sessao_a.request("POST", f"{P}/fatores/{fid}/amostras",
                          content='{"amostras":[{"lon":-47.9,"lat":-15.8,"valor":1e400}]}',
                          headers={"Content-Type": "application/json"})
    assert ra.status_code == 422, (ra.status_code, ra.text[:200])
    # controle positivo: valor finito grava
    rb = sessao_a.post(f"{P}/fatores/{fid}/amostras", json={"amostras": [{"lon": -47.9, "lat": -15.8, "valor": 1.0}]})
    assert rb.status_code == 201, rb.text
