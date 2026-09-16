"""Adversário da linha L3 (motor AMC), achado de API sobre a base `wt/uniao` (16/09/2026) — item
L3-01-b-unidades.

Reproduzido 2 de 2 vezes, isolado (`tests/api/amc/test_unidades.py::test_e2e_da_api_do_conjunto`
sozinho, sem mais nada rodando no arquivo): depois que `unidades.gerar_grade` grava a grade e a
ficha do conjunto reporta `n_unidades > 50` (confirmado por GET /api/amc/conjuntos/{id}), a MESMA
sessão pedindo `GET /api/amc/conjuntos/{id}/unidades?limite=10` volta com `features: []` — zero
feições — em vez das 10 esperadas.

Uma reprodução equivalente escrita à mão pelo adversário, no MESMO estilo (POST → gerar_grade com
ContextoDeTeste → GET → GET unidades), NÃO reproduziu o sumiço em duas tentativas: veio com as
features completas. Isso é compatível com dois cenários, e o adversário não teve como isolar qual:
(a) uma contaminação genuína e específica de `test_unidades.py` (algo no arquivo, não no motor); ou
(b) uma corrida com outra sessão de agente na MESMA trilha `plat_tuniao` (o brief comum descreve
várias trilhas paralelas; `plat.amc_unidade` não tem coluna de dono do teste, só `conjunto_id`, e um
`DELETE` de outra suíte rodando ao mesmo tempo nesta tabela poderia explicar o sumiço sem tocar
`amc_conjunto_unidade.n_unidades`, que já estava gravado antes).

Este teste REUSA as funções do arquivo original (não a reimplementação do adversário) para eliminar
qualquer divergência de parâmetro como causa. Ele fica xfail(strict=True): se voltar a passar sem
que ninguém tenha investigado a causa (a) ou (b) acima, alguém precisa remover este marcador com o
motivo escrito — nunca por engano."""

from __future__ import annotations

import pytest

from app.amc import unidades
from tests.api.amc.test_unidades import PREFIXO, ContextoDeTeste, _retangulo_de


@pytest.mark.xfail(
    strict=True,
    reason="GET /api/amc/conjuntos/{id}/unidades voltou com features=[] apesar de n_unidades > 50 "
           "gravado e confirmado por GET /api/amc/conjuntos/{id} — reproduzido 2/2 vezes isolando "
           "tests/api/amc/test_unidades.py::test_e2e_da_api_do_conjunto sozinho nesta base wt/uniao "
           "em 16/09/2026. Causa não isolada pelo adversário (ver docstring do módulo): pode ser "
           "escrita/leitura do motor ou corrida com outra sessão na mesma trilha compartilhada. "
           "Comando para reproduzir a versão original: bash laco/roda_teste.sh "
           "tests/api/amc/test_unidades.py::test_e2e_da_api_do_conjunto -q",
)
def test_unidades_aparecem_na_listagem_depois_da_grade_pronta(sessao_a, tenant_a):
    area = _retangulo_de(20.0)
    r = sessao_a.post("/api/amc/conjuntos", json={"nome": f"{PREFIXO} adv-l31", "tipo": "quadrada",
                                                  "lado_m": 500.0, "area_estudo": area})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    try:
        unidades.gerar_grade(ContextoDeTeste(tenant_a), cid)
        depois = sessao_a.get(f"/api/amc/conjuntos/{cid}").json()
        assert depois["n_unidades"] and depois["n_unidades"] > 0
        pagina = sessao_a.get(f"/api/amc/conjuntos/{cid}/unidades?limite=10").json()
        assert len(pagina["features"]) == min(10, depois["n_unidades"]), (
            f"n_unidades={depois['n_unidades']} mas a página trouxe {len(pagina['features'])} feições"
        )
    finally:
        sessao_a.delete(f"/api/amc/conjuntos/{cid}")
