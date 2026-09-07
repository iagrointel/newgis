"""Núcleo da ingestão vetorial (item L0-04-ingest-vetor; ADR 0005), reduzido a 4 formatos nesta passagem:
shapefile (zip), GeoPackage, GeoJSON, CSV (lat/lon). Portão do item pai: cada formato importa por upload e
aparece no catálogo; CRS errado/ausente é perguntado, não assumido; feições inválidas contadas e corrigidas com
relatório; teste automatizado com arquivo de cada formato (dado aberto, `tests/dados/gerar.py`); tamanho máximo e
cota do inquilino aplicados. Refutação do item pai: shapefile sem `.prj`, GeoJSON com polígono
auto-intersectado, CSV com vírgula decimal — cada um importa certo ou recusa com mensagem exata."""

import pytest

from tests.api.ingestao.conftest import GERADOS
from tests.api.test_rls import contexto, ids_por_slug


def _contexto_admin(con, ids: dict, slug: str = "demo"):
    """`contexto()` com o usuario_id REAL do admin do inquilino (plat.item.p_item_ler exige `plat.pode_ler(id)`,
    que é falso para usuario_id=0 em item privado — usuario_id=0 só serve para as tabelas de camada, cuja RLS
    é só por tenant_id)."""
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")


ITEM = "L0-04-ingest-vetor"
pytestmark = pytest.mark.skipif(not GERADOS.exists(), reason="rode `venv/bin/python tests/dados/gerar.py` antes")


def _tabela_de(cur, item_id: str) -> tuple[str, str]:
    cur.execute("SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item WHERE id=%s::uuid",
                (item_id,))
    r = cur.fetchone()
    return r["schema"], r["tabela"]


def test_gpkg_importa_e_publica_no_catalogo(ingestor_a, conexao_plat_app, medida):
    importacao_id, insp = ingestor_a.importar("cobertura.gpkg", "gpkg")
    assert insp["estado"] == "proposta", insp
    assert insp["proposta"]["feicoes"] == 80
    assert insp["proposta"]["geometria"]["escolhida"] == "MultiPolygon"
    assert insp["proposta"]["crs"]["srid"] == 4674  # do gpkg_spatial_ref_sys, sem pergunta
    assert not insp["proposta"]["perguntas"]

    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 80

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
        assert cur.fetchone()["n"] == 80
        cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (tabela,))
        r = cur.fetchone()
        assert r["relrowsecurity"] and r["relforcerowsecurity"], "FORCE ROW LEVEL SECURITY ausente"


def test_geojson_importa(ingestor_a):
    importacao_id, insp = ingestor_a.importar("cobertura.geojson", "geojson")
    assert insp["proposta"]["feicoes"] == 80
    assert insp["proposta"]["crs"]["origem"] == "crs_legado"  # o gerador escreveu com t_srs 4674, sem RFC7946 puro
    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 80


def test_csv_lat_lon_virgula_decimal_importa(ingestor_a, conexao_plat_app):
    """ATAQUE do item pai: CSV com `;` e vírgula decimal (dado real de lugares de Guarulhos, OSM). A proposta
    pergunta o CRS (nenhum CSV declara um) e os valores decimais batem com o arquivo de origem."""
    importacao_id, insp = ingestor_a.importar("lugares_pv.csv", "csv")
    proposta = insp["proposta"]
    assert proposta["feicoes"] == 40
    assert proposta["geometria"]["escolhida"] == "Point"
    assert "crs" in proposta["perguntas"]
    assert proposta["csv"]["separador_origem"] == ";"
    assert proposta["csv"]["decimal_origem"] == ","
    assert "latitude" in proposta["csv"]["colunas_decimal_virgula"]

    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 40

    linhas_origem = (GERADOS / "lugares_pv.csv").read_text(encoding="utf-8-sig").splitlines()[1:]
    primeira = linhas_origem[0].split(";")
    lat_esperada = float(primeira[2].replace(",", "."))
    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        cur.execute(f'SELECT latitude FROM "{schema}"."{tabela}" ORDER BY fid LIMIT 1')
        lat_gravada = float(cur.fetchone()["latitude"])
    assert abs(lat_gravada - lat_esperada) < 1e-6, (lat_gravada, lat_esperada)


def test_csv_aspas_desbalanceadas_recusa_com_mensagem_exata(ingestor_a):
    """ATAQUE (formato-espelho do pai, seção 4.3 do ADR): aspas desbalanceadas nunca engolem linha em silêncio —
    a inspeção recusa com a linha exata."""
    importacao_id, insp = ingestor_a.importar("csv_aspas.csv", "csv")
    assert insp["estado"] == "falhou"
    assert "aspas desbalanceadas na linha 2" in insp["erro"]


def test_shapefile_zip_importa(ingestor_a):
    importacao_id, insp = ingestor_a.importar("cobertura_shp.zip", "shapefile.zip", content_type="application/zip")
    proposta = insp["proposta"]
    assert proposta["feicoes"] == 80
    assert proposta["crs"]["origem"] == "prj" and proposta["crs"]["srid"] == 4674
    assert proposta["codificacao"]["origem"] == "cpg"
    assert not proposta["perguntas"]
    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 80


def test_shapefile_sem_prj_pergunta_crs_e_importa_apos_confirmar(ingestor_a):
    """ATAQUE do item pai: shapefile sem `.prj` — CRS SRID 0 é o erro documentado no ADR (seção 0.3); a inspeção
    tem de perguntar, nunca assumir, e a carga só roda com o SRID confirmado."""
    importacao_id, insp = ingestor_a.importar("cobertura_semprj.zip", "shapefile.zip", content_type="application/zip")
    proposta = insp["proposta"]
    assert proposta["crs"]["origem"] == "nenhum" and proposta["crs"]["srid"] is None
    assert proposta["crs"]["perguntar"] is True
    assert proposta["crs"]["sugestao"] == 4674  # extent dentro do Brasil, em graus
    assert proposta["perguntas"] == ["crs"]

    # confirmar sem responder a pergunta pendente -> 422 perguntas_pendentes (nunca assume)
    r = ingestor_a.sessao.put(f"/api/importacoes/{importacao_id}/confirmar", json={})
    assert r.status_code == 422 and r.json()["erro"] == "perguntas_pendentes"
    assert "crs" in r.json()["detalhe"]["perguntas"]

    final = ingestor_a.confirmar(importacao_id, {"crs": {"srid": 4674}})
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 80


def test_geojson_poligono_autointersectado_e_corrigido_com_relatorio(ingestor_a):
    """ATAQUE do item pai: GeoJSON com polígono auto-intersectado (gravata) — ST_MakeValid corrige, o relatório
    conta quantas (1 de 3), e os fids corrigidos aparecem no relatório."""
    importacao_id, insp = ingestor_a.importar("gravata.geojson", "geojson")
    proposta = insp["proposta"]
    assert proposta["feicoes"] == 3
    assert proposta["validade"]["invalidas"] == 1
    assert proposta["validade"]["acao"] == "corrigir"
    assert "Self-intersection" in proposta["validade"]["exemplo"]

    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["corrigidas"] == 1
    assert final["relatorio"]["descartadas"] == 0
    assert len(final["relatorio"]["fids_corrigidos"]) == 1


def test_formato_nao_suportado_recusa_antes_de_qualquer_job(ingestor_a):
    obj = ingestor_a.enviar_arquivo(GERADOS / "cobertura.gpkg")
    item_id = ingestor_a.item_arquivo(obj, "cobertura.gpkg")
    r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "kml"})
    assert r.status_code == 422 and r.json()["erro"] == "formato_nao_suportado"


def test_conteudo_nao_corresponde_ao_tipo_declarado(ingestor_a):
    """gpkg (sqlite) declarado como geojson -> recusado pelos bytes, nunca em silêncio."""
    obj = ingestor_a.enviar_arquivo(GERADOS / "cobertura.gpkg")
    item_id = ingestor_a.item_arquivo(obj, "cobertura.gpkg")
    r = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "geojson"})
    assert r.status_code == 422 and r.json()["erro"] == "conteudo_nao_corresponde"


def test_dois_inquilinos_nao_veem_camada_um_do_outro(ingestor_a, sessao_b, conexao_plat_app):
    """RLS FORCE cruzada: o item some para o inquilino B (catálogo) e a tabela devolve 0 linhas para plat_app no
    contexto de B, mesmo sendo dono (plat_app) da tabela física."""
    importacao_id, _ = ingestor_a.importar("cobertura.gpkg", "gpkg")
    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final

    assert sessao_b.get(f"/api/itens/{final['item_id']}").status_code == 404

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
    contexto(conexao_plat_app, ids["demo2"])  # plat_app no contexto do OUTRO inquilino
    with conexao_plat_app.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
        assert cur.fetchone()["n"] == 0


def test_importar_o_mesmo_arquivo_duas_vezes_em_paralelo_nao_falha(ingestor_a):
    """Refutação do item pai (L0-04-c): duas importações do MESMO arquivo, dois item_id/tabelas distintos, as
    duas terminam (a chave do job serializa a carga por ARQUIVO, não por importação)."""
    obj = ingestor_a.enviar_arquivo(GERADOS / "cobertura.gpkg")
    item_id = ingestor_a.item_arquivo(obj, "cobertura.gpkg")
    r1 = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "gpkg"})
    r2 = ingestor_a.sessao.post("/api/importacoes", json={"arquivo_id": item_id, "formato": "gpkg"})
    assert r1.status_code == 202 and r2.status_code == 202
    from tests.api.ingestao.conftest import esperar_job

    j1 = esperar_job(ingestor_a.sessao, r1.json()["job_id"])
    j2 = esperar_job(ingestor_a.sessao, r2.json()["job_id"])
    assert j1["estado"] == j2["estado"] == "concluido"
    imp1 = ingestor_a.sessao.get(f"/api/importacoes/{r1.json()['importacao_id']}").json()
    imp2 = ingestor_a.sessao.get(f"/api/importacoes/{r2.json()['importacao_id']}").json()
    assert imp1["item_id"] != imp2["item_id"]
    final1 = ingestor_a.confirmar(imp1["id"])
    final2 = ingestor_a.confirmar(imp2["id"])
    assert final1["estado"] == final2["estado"] == "concluida"
    assert final1["item_id"] != final2["item_id"]


def test_cota_excedida_nao_cria_tabela(ingestor_a, conexao_plat_app, env):
    """Cota do inquilino excedida -> falha ANTES de criar tabela (invariante: 0 tabela órfã). Mexe só em
    `uso_reservado_bytes` (a reserva de OUTRAS cargas em curso), nunca em `cota_bytes`: `cota_bytes` também é a
    cota do BUCKET do Garage (L0-11) e é um valor COMPARTILHADO entre suítes que rodam em paralelo no mesmo
    inquilino `demo` neste turno — mexer nele derrubou o upload de outros testes por engano (MEDIDO: a cota do
    bucket ficou travada em 1 byte depois de uma corrida com outra suíte usando o mesmo `cota_bytes`)."""
    ids = ids_por_slug(conexao_plat_app)
    importacao_id, insp = ingestor_a.importar("cobertura.gpkg", "gpkg")
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT cota_bytes, uso_reservado_bytes FROM plat.tenant WHERE id = %s", (ids["demo"],))
        antes = cur.fetchone()
        # reserva quase toda a cota para OUTRA carga (fictícia): sobra menos que a estimativa (bytes×3) do gpkg
        cur.execute("UPDATE plat.tenant SET uso_reservado_bytes = cota_bytes - 1000 WHERE id = %s", (ids["demo"],))
    conexao_plat_app.commit()
    try:
        final = ingestor_a.confirmar(importacao_id)
        assert final["estado"] == "falhou", final
        assert "cota" in (final["erro"] or "").lower()
        _contexto_admin(conexao_plat_app, ids)
        # invariante geral do item (ADR 6.2-9): toda tabela d_demo.c_* tem item, todo item camada_vetorial tem tabela
        with conexao_plat_app.cursor() as cur:
            # o schema de dado é o da INSTALAÇÃO (plat.camada_schema_prefixo): em produção `d_demo`, numa
            # trilha `d_plat_t<T>_demo`. Com 'd_demo' fixo, o invariante media o schema de PRODUÇÃO —
            # e contava as tabelas que outras trilhas deixaram lá (87 em 07/09/2026).
            cur.execute(
                "SELECT count(*) AS n FROM pg_tables t WHERE t.schemaname = plat.camada_schema_prefixo() || 'demo' "
                "AND t.tablename LIKE 'c\\_%' "
                "AND NOT EXISTS (SELECT 1 FROM plat.item i WHERE i.tipo='camada_vetorial' "
                "AND i.dados->>'tabela' = t.tablename)"
            )
            assert cur.fetchone()["n"] == 0, "tabela órfã (sem item) encontrada"
    finally:
        contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
        with conexao_plat_app.cursor() as cur:
            cur.execute("UPDATE plat.tenant SET uso_reservado_bytes = %s WHERE id = %s",
                        (antes["uso_reservado_bytes"], ids["demo"]))
        conexao_plat_app.commit()


def test_crs_confirmado_pelo_usuario_nunca_e_reprojetado(ingestor_a):
    """Refutação do item pai (CRS mentido): a carga NUNCA reprojeta (-a_srs, nunca -t_srs, ADR seção 9) — grava
    exatamente o SRID que o usuário confirmou, mesmo quando ele escolhe um SRID diferente do sugerido pela
    inspeção; a carga aceita e não finge ter certeza sobre o dado."""
    importacao_id, insp = ingestor_a.importar("cobertura_semprj.zip", "shapefile.zip", content_type="application/zip")
    assert insp["proposta"]["crs"]["sugestao"] == 4674
    final = ingestor_a.confirmar(importacao_id, {"crs": {"srid": 3857}})  # o usuário escolhe outro SRID válido
    assert final["estado"] == "concluida", final
