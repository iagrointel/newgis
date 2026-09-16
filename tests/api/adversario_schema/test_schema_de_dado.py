"""FURO fora do alcance do reescritor: o dado do inquilino não mora em `plat`, mora em `d_<slug>` --
um nome que NÃO contém a palavra `plat` e que, por isso, nenhuma reescrita alcança. Produção,
homologação e todas as trilhas dividem `d_demo`, `d_demo2` e `d_plataforma`.
"""

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
CARREGAR = RAIZ / "app" / "ingestao" / "carregar.py"


# FURO F8 fechado em 16/09/2026 (commit fac1db70f, "Schema de dado de camada carrega a instalacao
# (achado F8 do adversario)"): app/ingestao/carregar.py agora monta o schema com
# plat.camada_schema_prefixo(), que poe a instalacao no prefixo em vez de so "d_" mais o slug.
# Achado original: o schema era "d_" concatenado ao slug sem prefixo de ambiente, e
# db/migracoes/029_ingestao_vetor.sql criava o mesmo nome do lado do banco -- producao, homologacao
# e trilha caiam no mesmo d_<slug>.
def test_schema_de_dado_do_inquilino_inclui_o_ambiente():
    fonte = CARREGAR.read_text(encoding="utf-8")
    assert 'f"d_{slug}"' not in fonte, (
        "carregar.py deriva o schema de dado so do slug: producao e trilha caem no mesmo d_<slug>"
    )


# FURO F8 (medido) fechado em 16/09/2026 (commit fac1db70f, "Schema de dado de camada carrega a
# instalacao (achado F8 do adversario)"): laco/trilha_ambiente.sh deixou de dar GRANT USAGE, CREATE
# a role da trilha em schema `d\_%` de producao. Achado original: a trilha ganhava privilegio em
# todo schema `d_<slug>` que ja existisse -- inclusive `d_demo`, dono plat_app, 78 tabelas medidas
# em 07/09/2026 -- e podia criar/apagar tabela dentro do schema de dado de producao.
def test_trilha_nao_escreve_no_schema_de_dado_de_producao(con):
    with con.cursor() as cur:
        cur.execute("SELECT nspname, pg_get_userbyid(nspowner) AS dono FROM pg_namespace "
                    "WHERE nspname LIKE 'd\\_%' AND pg_get_userbyid(nspowner) = 'plat_app'")
        producao = [r["nspname"] for r in cur.fetchall()]
        if not producao:
            pytest.skip("nenhum schema de dado de producao neste banco")
        cur.execute("SELECT current_user AS eu")
        eu = cur.fetchone()["eu"]
        cur.execute("SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s) "
                    "AND has_schema_privilege(%s, nspname, 'CREATE')", (producao, eu))
        podem = [r["nspname"] for r in cur.fetchall()]
    assert not podem, f"{eu} tem CREATE nos schemas de dado de producao: {podem}"
