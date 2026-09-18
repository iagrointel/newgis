"""Item L1-02-d — a cláusula "página interna de status com taxa de acerto do cache por dia".

A contagem é medida aqui sobre linhas de log SINTÉTICAS, de propósito: a aritmética é a parte que pode
errar, e medi-la sem journal, sem nginx e sem rede torna a prova reprodutível em qualquer máquina. A
leitura do journal de verdade é exercida pela rota, em tests/api/imagens/test_l102d_cache_status_rota.py.
"""

from __future__ import annotations

import json

from app.imagens import cache_status


def _linha(dia: str, estado: str | None, hora: str = "10:00:00") -> str:
    registro = {"ts": f"{dia}T{hora}+00:00", "fonte": "nginx", "status": 200, "rota": "/svc/<token>/x"}
    if estado is not None:
        registro["cache"] = estado
    return json.dumps(registro)


def test_taxa_por_dia_separa_os_dias():
    linhas = ([_linha("2026-09-17", "HIT")] * 9 + [_linha("2026-09-17", "MISS")]
              + [_linha("2026-09-18", "HIT")] + [_linha("2026-09-18", "MISS")] * 3)
    r = cache_status.resumir(linhas)
    assert r["estado"] == "ok"
    por_dia = {d["dia"]: d for d in r["dias"]}
    assert por_dia["2026-09-17"]["taxa_de_acerto"] == 0.9
    assert por_dia["2026-09-18"]["taxa_de_acerto"] == 0.25


def test_revalidated_e_stale_contam_como_acerto():
    """A resposta veio do cache; `REVALIDATED` só foi confirmar validade com o upstream."""
    r = cache_status.resumir([_linha("2026-09-18", e) for e in ("REVALIDATED", "STALE", "UPDATING", "HIT")])
    assert r["dias"][0]["acertos"] == 4
    assert r["dias"][0]["taxa_de_acerto"] == 1.0


def test_requisicao_fora_de_zona_de_cache_nao_rebaixa_a_taxa():
    """`-` é requisição que não passou por cache nenhum. Contar como erro inventaria uma perda."""
    r = cache_status.resumir([_linha("2026-09-18", "HIT"), _linha("2026-09-18", "-"),
                              _linha("2026-09-18", "")])
    dia = r["dias"][0]
    assert dia["sem_cache"] == 2
    assert dia["pedidos_com_cache"] == 1
    assert dia["taxa_de_acerto"] == 1.0


def test_sem_o_campo_cache_a_resposta_e_sem_dado_e_nao_zero():
    """A distinção que o módulo existe para fazer: taxa desconhecida não é taxa zero."""
    r = cache_status.resumir([_linha("2026-09-18", None) for _ in range(5)])
    assert r["estado"] == "sem_dado"
    assert r["dias"] == []
    assert "plat_json_cache" in r["por_que"]


def test_sem_linhas_nenhuma_diz_sem_linhas():
    r = cache_status.resumir([])
    assert r["estado"] == "sem_linhas"


def test_linha_que_nao_e_json_e_ignorada_sem_derrubar():
    r = cache_status.resumir(["isto nao e json", _linha("2026-09-18", "HIT")])
    assert r["estado"] == "ok"
    assert r["dias"][0]["acertos"] == 1


def test_estado_desconhecido_do_nginx_e_contado_e_nao_descartado():
    """Se o nginx ganhar um estado novo, ele não pode sumir da contagem em silêncio."""
    r = cache_status.resumir([_linha("2026-09-18", "HIT"), _linha("2026-09-18", "COISA_NOVA")])
    dia = r["dias"][0]
    assert dia["acertos"] + dia["erros"] + dia["sem_cache"] == 2
