"""07/09: os testes do geocodificador exigem a UF de demonstração instalada (RR, scripts/geocodificador_instalar_uf.py).
Numa base por trilha (fila de junção, homologação) ela não está carregada por desenho (D21/D28, disco a 95 %):
o módulo é PULADO com o motivo escrito, nunca aproximado. Na árvore principal, com RR carregada, roda inteiro."""

import pytest


@pytest.fixture(autouse=True)
def _exige_uf_instalada(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT to_regclass('plat.geo_instalacao') IS NOT NULL AS tem")
        if not cur.fetchone()["tem"]:
            pytest.skip("plat.geo_instalacao não existe nesta base")
        cur.execute("SELECT count(*) AS n FROM plat.geo_instalacao")
        if not cur.fetchone()["n"]:
            pytest.skip("nenhuma UF do geocodificador instalada nesta base (RR na demo; base por trilha não carrega)")
    conexao_plat_app.rollback()
