"""Cláusula de VOLUME do portão do item L0-04-c-tabela-camada: "shapefile de 100 mil feições (dado aberto, ex.
setores censitários de um estado) importa e aparece na lista em ≤ 60 s medido (medida tempo_import_100k_s)".

Dado aberto real: malha de setores censitários do Censo 2022 do IBGE, os 100.000 primeiros setores de São Paulo
por `cd_setor` (SIRGAS 2000, EPSG:4674, MULTIPOLYGON) — gerador `tests/dados/gerar_100k.py`, determinístico.

Teste LENTO (sobe 75 MiB e carrega 100 mil feições): fora da rodada curta por `-m "not lento"`.
"""

import time

import pytest

from tests.api.ingestao.conftest import GERADOS, esperar_importacao, esperar_job
from tests.api.test_rls import contexto, ids_por_slug

ARQUIVO = GERADOS / "setores_sp_100k.zip"
N_ESPERADO = 100_000
TETO_S = 60.0

pytestmark = [
    pytest.mark.lento,
    pytest.mark.skipif(not ARQUIVO.exists(),
                       reason="rode `venv/bin/python tests/dados/gerar_100k.py` antes (75 MiB, dado aberto IBGE)"),
]


def _contexto_admin(con, ids: dict, slug: str = "demo"):
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")


def test_shapefile_de_100_mil_feicoes_importa_e_aparece_na_lista(ingestor_a, conexao_plat_app, medida):
    sessao = ingestor_a.sessao

    t0 = time.monotonic()
    objeto = ingestor_a.enviar_arquivo(ARQUIVO)
    t_upload = time.monotonic() - t0
    item_arquivo = ingestor_a.item_arquivo(objeto, ARQUIVO.name)

    t0 = time.monotonic()
    r = sessao.post("/api/importacoes", json={"arquivo_id": item_arquivo, "formato": "shapefile.zip"})
    assert r.status_code == 202, r.text
    importacao_id = r.json()["importacao_id"]
    esperar_job(sessao, r.json()["job_id"], timeout=300)
    t_inspecao = time.monotonic() - t0
    insp = sessao.get(f"/api/importacoes/{importacao_id}").json()
    assert insp["estado"] == "proposta", insp
    assert insp["proposta"]["feicoes"] == N_ESPERADO, insp["proposta"]["feicoes"]
    assert insp["proposta"]["crs"]["srid"] == 4674, insp["proposta"]["crs"]

    # o relógio da cláusula: confirmar -> a camada aparece na lista do catálogo
    t0 = time.monotonic()
    r = sessao.put(f"/api/importacoes/{importacao_id}/confirmar", json={})
    assert r.status_code == 202, r.text
    esperar_job(sessao, r.json()["job_id"], timeout=300)
    final = esperar_importacao(sessao, importacao_id, ("concluida", "falhou"), timeout=60)
    assert final["estado"] == "concluida", final
    item_id = final["item_id"]
    ingestor_a.camadas.append(item_id)
    achou = None
    while achou is None and time.monotonic() - t0 < 300:
        pagina = sessao.get("/api/itens", params={"tipo": "camada_vetorial", "limite": 100}).json()
        achou = next((i for i in pagina.get("itens", []) if i["id"] == item_id), None)
        if achou is None:
            time.sleep(0.2)
    t_import = time.monotonic() - t0
    assert achou is not None, "camada não apareceu na lista /api/itens"

    assert final["relatorio"]["feicoes_carregadas"] == N_ESPERADO, final["relatorio"]

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT dados->>'schema' AS s, dados->>'tabela' AS t FROM plat.item WHERE id=%s::uuid",
                    (item_id,))
        r2 = cur.fetchone()
        cur.execute(f'SELECT count(*) AS n FROM "{r2["s"]}"."{r2["t"]}"')
        assert cur.fetchone()["n"] == N_ESPERADO
        cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (r2["t"],))
        rls = cur.fetchone()
        assert rls["relrowsecurity"] and rls["relforcerowsecurity"], "RLS ausente na tabela de 100 mil feições"

    gravar = medida("L0-04-c-tabela-camada")
    gravar("tempo_import_100k_s", round(t_import, 1), "s",
           "PUT /api/importacoes/{id}/confirmar até a camada aparecer em GET /api/itens?tipo=camada_vetorial; "
           "shapefile dos 100.000 primeiros setores censitários de São Paulo (IBGE, Censo 2022, EPSG:4674); "
           "tests/api/ingestao/test_ingestao_100k.py")
    gravar("tempo_upload_100k_s", round(t_upload, 1), "s",
           "POST /api/arquivos do zip de 75,2 MiB (fora do relógio da cláusula, medido à parte)")
    gravar("tempo_inspecao_100k_s", round(t_inspecao, 1), "s",
           "POST /api/importacoes até o job ingestao.inspecionar concluir (fora do relógio da cláusula)")
    assert t_import <= TETO_S, f"tempo_import_100k_s = {t_import:.1f} s (teto {TETO_S} s)"
