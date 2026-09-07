"""FURO fora do alcance do reescritor: o dado do inquilino não mora em `plat`, mora em `d_<slug>` --
um nome que NÃO contém a palavra `plat` e que, por isso, nenhuma reescrita alcança. Produção,
homologação e todas as trilhas dividem `d_demo`, `d_demo2` e `d_plataforma`.
"""

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
CARREGAR = RAIZ / "app" / "ingestao" / "carregar.py"


@pytest.mark.xfail(strict=True, reason="FURO F8: app/ingestao/carregar.py:102 monta `schema = f'd_{slug}'` "
                                       "sem prefixo de ambiente, e db/migracoes/029_ingestao_vetor.sql:103, "
                                       ":172 e :190 criam `'d_' || p_slug` do mesmo jeito. O job de carga "
                                       "ainda faz `DROP TABLE IF EXISTS \"d_<slug>\".\"<tabela>\"` "
                                       "(carregar.py:113) e entrega esse nome ao ogr2ogr em `-nln` "
                                       "(carregar.py:172) -- subprocesso que nem passa por psycopg2. "
                                       "Conserto ja existe no ramo wt/il004hexpor (plat.camada_schema_prefixo), "
                                       "nao esta em master")
def test_schema_de_dado_do_inquilino_inclui_o_ambiente():
    fonte = CARREGAR.read_text(encoding="utf-8")
    assert 'f"d_{slug}"' not in fonte, (
        "carregar.py deriva o schema de dado so do slug: producao e trilha caem no mesmo d_<slug>"
    )


@pytest.mark.xfail(strict=True, reason="FURO F8 (medido): laco/trilha_ambiente.sh secao c2 DA `GRANT USAGE, "
                                       "CREATE` a role da trilha em todo schema `d\\_%` que ja exista -- "
                                       "inclusive `d_demo`, que e de producao (dono plat_app, 78 tabelas "
                                       "medidas em 07/09/2026). A trilha pode criar e apagar tabela dentro "
                                       "do schema de dado de producao")
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
