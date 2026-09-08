"""HARD-03 — adversário do motor AMC/multiescala (L3) e dos apps (L5) sobre master. Ataca: peso negativo/zero/NaN,
número de fatores/amostras/células acima do teto, e documento de app que referencia item de outro inquilino. O
caminho de peso/valor INFINITO é um achado à parte (H3-L3-01): fix + regressão em wt/cx4fix2. Cada ataque com
controle positivo. Só roda em trilha (conftest do pacote)."""

from __future__ import annotations

import json
import secrets

from tests.api.catalogo.conftest import DADOS_POR_TIPO
from tests.api.conftest import PREFIXO_TESTE

P = "/api/multiescala"


def _retangulo():
    x, y = -47.9, -15.8
    return {"type": "Polygon", "coordinates": [[[x, y], [x + 0.02, y], [x + 0.02, y + 0.02], [x, y + 0.02], [x, y]]]}


def _conjunto(sessao):
    r = sessao.post(f"{P}/conjuntos", json={"nome": f"zt-adv-{secrets.token_hex(3)}", "area": _retangulo()})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _fator(sessao, valor=1.0):
    r = sessao.post(f"{P}/fatores", json={"nome": f"zt-f-{secrets.token_hex(3)}", "resolucao_fonte_m": 100.0,
                                          "papel": "atrai", "unidade": "un", "fonte": "amostra de teste"})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    pts = [{"lon": -47.9 + 0.005 * i, "lat": -15.8 + 0.005 * i, "valor": valor} for i in range(4)]
    ra = sessao.post(f"{P}/fatores/{fid}/amostras", json={"amostras": pts})
    assert ra.status_code == 201, ra.text
    return fid


def _post_macro(sessao, cid, fatores, resolucao_m=500.0):
    corpo = {"resolucao_m": resolucao_m, "fatores": fatores, "aprovacao_tipo": "top_pct", "aprovacao_valor": 50}
    return sessao.request("POST", f"{P}/conjuntos/{cid}/macro", content=json.dumps(corpo),
                          headers={"Content-Type": "application/json"})


def test_peso_negativo_zero_e_nan_recusados(sessao_a):
    cid = _conjunto(sessao_a)
    fid = _fator(sessao_a)
    try:
        for peso in (-1.0, 0.0, float("nan")):
            r = _post_macro(sessao_a, cid, [{"fator_id": fid, "peso": peso}])
            assert r.status_code == 422, (peso, r.status_code, r.text[:160])
        r = _post_macro(sessao_a, cid, [{"fator_id": fid, "peso": 1.0}])  # controle positivo
        assert r.status_code == 201, r.text
    finally:
        sessao_a.delete(f"{P}/conjuntos/{cid}")


def test_numero_de_fatores_acima_do_teto_recusado(sessao_a):
    from app import limites
    cid = _conjunto(sessao_a)
    fid = _fator(sessao_a)
    try:
        demais = [{"fator_id": fid, "peso": 1.0} for _ in range(limites.ESCALA_FATORES_MAX + 5)]
        r = _post_macro(sessao_a, cid, demais)
        assert r.status_code == 422, (r.status_code, r.text[:160])
    finally:
        sessao_a.delete(f"{P}/conjuntos/{cid}")


def test_amostras_acima_do_lote_recusadas(sessao_a):
    from app import limites
    r = sessao_a.post(f"{P}/fatores", json={"nome": f"zt-f-{secrets.token_hex(3)}", "resolucao_fonte_m": 100.0,
                                            "papel": "atrai", "unidade": "un", "fonte": "amostra de teste"})
    fid = r.json()["id"]
    pts = [{"lon": -47.9, "lat": -15.8, "valor": 1.0} for _ in range(limites.ESCALA_AMOSTRAS_LOTE_MAX + 5)]
    ra = sessao_a.post(f"{P}/fatores/{fid}/amostras", json={"amostras": pts})
    assert ra.status_code == 422, (ra.status_code, ra.text[:160])


def test_grade_de_unidades_acima_do_teto_recusada(sessao_a):
    """Resolução de 1 m sobre a área (~4,8 mi células) passa do teto de 250 mil: o motor conta antes de
    materializar e recusa 4xx, nunca estoura memória nem 500. Controle: resolução grande executa."""
    cid = _conjunto(sessao_a)
    fid = _fator(sessao_a)
    try:
        r = _post_macro(sessao_a, cid, [{"fator_id": fid, "peso": 1.0}], resolucao_m=1.0)
        assert 400 <= r.status_code < 500, (r.status_code, r.text[:160])
        assert "célula" in r.text or "celula" in r.text or "grade" in r.text, r.text[:160]
        r = _post_macro(sessao_a, cid, [{"fator_id": fid, "peso": 1.0}], resolucao_m=500.0)
        assert r.status_code == 201, r.text
    finally:
        sessao_a.delete(f"{P}/conjuntos/{cid}")


def _item(sessao, tipo="mapa"):
    r = sessao.post("/api/itens", json={"tipo": tipo, "titulo": f"{PREFIXO_TESTE} {secrets.token_hex(3)}",
                                        "dados": DADOS_POR_TIPO[tipo]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_app_referenciando_item_de_outro_inquilino_recusado(sessao_a, sessao_b):
    """Documento de app aponta mapas por uuid (dados.corpo.mapas). Referenciar item de B a partir de A é recusado
    (relacoes.sincronizar confere o destino sob RLS). Controle: referência ao próprio mapa é aceita."""
    mapa_b = _item(sessao_b, "mapa")
    mapa_a = _item(sessao_a, "mapa")
    try:
        r = sessao_a.post("/api/itens", json={"tipo": "app", "titulo": f"{PREFIXO_TESTE} app",
                                              "dados": {"tipo": "app", "esquema_versao": 1,
                                                        "corpo": {"mapas": [mapa_b]}}})
        assert r.status_code in (403, 422), (r.status_code, r.text[:200])
        assert "inquilino" in r.text or "inexistente" in r.text, r.text[:200]
        r = sessao_a.post("/api/itens", json={"tipo": "app", "titulo": f"{PREFIXO_TESTE} app ok",
                                              "dados": {"tipo": "app", "esquema_versao": 1,
                                                        "corpo": {"mapas": [mapa_a]}}})
        assert r.status_code == 201, r.text
        sessao_a.delete(f"/api/itens/{r.json()['id']}")
    finally:
        sessao_a.delete(f"/api/itens/{mapa_a}")
        sessao_b.delete(f"/api/itens/{mapa_b}")
