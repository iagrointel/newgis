"""Desempenho da tabela de atributos em camada de 1 milhão de linhas (portão do item L2-01-g-tabela-atributos:
"primeira página <= 300 ms p95 e ordenar por coluna indexada <= 300 ms p95").

Marcado `lento` porque monta a camada do zero: 1.000.000 de feições com geometria, índice GIST, RLS e um índice
de ordenação. A tabela é criada com nome aleatório em `d_demo` e SOLTA no fim, sempre — inclusive se o teste
falhar. Nada de padrão de nome: só o nome exato que esta rodada criou.

A medida sai com a CARGA DA MÁQUINA ao lado (`carga_1min`, `ram_livre_gb`). Tempo medido sob disputa não diz
nada sobre o produto; sem o número da carga registrado, a medida não vale como prova."""

import os
import statistics
import time

import pytest

from tests.api.test_tabela_atributos import ITEM, _criar_camada

pytestmark = pytest.mark.lento

FEICOES = 1_000_000
ALVO_MS = 300
REPETICOES = 20


def _carga():
    return {"carga_1min": os.getloadavg()[0],
            "ram_livre_gb": round(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3, 2)}


def _p95(amostras):
    ordenadas = sorted(amostras)
    return ordenadas[max(0, int(round(0.95 * len(ordenadas))) - 1)]


@pytest.fixture(scope="module")
def camada_grande(sessao_a, env):
    item_id, _schema, _tabela, fechar = _criar_camada(sessao_a, env, FEICOES, indexar=["area_ha", "fid"])
    try:
        yield item_id
    finally:
        fechar()


def _medir(sessao, url, corpo):
    tempos = []
    for _ in range(REPETICOES):
        inicio = time.perf_counter()
        r = sessao.post(url, json=corpo)
        tempos.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200, r.text
    return tempos, r.json()


def test_primeira_pagina_e_ordenacao_por_coluna_indexada_em_1_milhao(sessao_a, camada_grande, medida):
    url = f"/api/camadas/{camada_grande}/tabela/linhas"
    gravar = medida(ITEM)
    carga = _carga()

    tempos_pagina, corpo = _medir(sessao_a, url, {"pagina": 1, "por_pagina": 50})
    assert corpo["total"] == FEICOES, corpo["total"]
    assert len(corpo["linhas"]) == 50
    p95_pagina = _p95(tempos_pagina)

    # reordenar não muda o total; a tela manda `contar: false` nesse caso (ver o comentário em
    # app/tabela/rotas.py). Medir com recontagem seria medir o `count(*)`, não a ordenação.
    tempos_ordem, corpo_ordem = _medir(sessao_a, url, {"pagina": 1, "por_pagina": 50, "contar": False,
                                                       "ordenar_por": "area_ha", "ordem": "asc"})
    assert corpo_ordem["total"] is None
    assert len(corpo_ordem["linhas"]) == 50
    p95_ordem = _p95(tempos_ordem)

    comando = ("bash laco/roda_teste.sh tests/api/test_tabela_atributos_1mi.py -q -m lento "
               "(PLAT_GRAVAR_MEDIDAS=1)")
    gravar("feicoes_da_camada_medida", FEICOES, "linhas", comando)
    gravar("primeira_pagina_p95_ms", round(p95_pagina, 1), "ms", comando)
    gravar("primeira_pagina_mediana_ms", round(statistics.median(tempos_pagina), 1), "ms", comando)
    gravar("ordenar_coluna_indexada_p95_ms", round(p95_ordem, 1), "ms", comando)
    gravar("ordenar_coluna_indexada_mediana_ms", round(statistics.median(tempos_ordem), 1), "ms", comando)
    tempos_contagem, _c = _medir(sessao_a, url, {"pagina": 1, "por_pagina": 50, "contar": True,
                                                 "ordenar_por": "area_ha", "ordem": "asc"})
    gravar("ordenar_com_recontagem_p95_ms", round(_p95(tempos_contagem), 1), "ms", comando)
    gravar("carga_1min", carga["carga_1min"], "media de processos", comando)
    gravar("ram_livre_gb", carga["ram_livre_gb"], "GB", comando)
    gravar("medido_em", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "UTC", comando)

    assert p95_pagina <= ALVO_MS, f"primeira página p95 {p95_pagina:.0f} ms (carga {carga})"
    assert p95_ordem <= ALVO_MS, f"ordenação indexada p95 {p95_ordem:.0f} ms (carga {carga})"


def test_pagina_1000_do_meio_da_camada_nao_repete_linha(sessao_a, camada_grande):
    """Rolar fundo (deslocamento grande) continua devolvendo página estável e sem repetição — é o que o
    adversário faz ao rolar cem páginas."""
    url = f"/api/camadas/{camada_grande}/tabela/linhas"
    vistos = set()
    for pagina in (1, 50, 100):
        corpo = sessao_a.post(url, json={"pagina": pagina, "por_pagina": 1000,
                                         "ordenar_por": "area_ha", "ordem": "asc"}).json()
        ids = [linha["id"] for linha in corpo["linhas"]]
        assert len(ids) == 1000
        assert not (set(ids) & vistos), f"página {pagina} repetiu linha de página anterior"
        vistos |= set(ids)
