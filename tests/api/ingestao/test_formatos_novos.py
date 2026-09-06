"""Formatos acrescentados pelo item L6-02-o-importacao-exportacao-formatos à ingestão (`app/ingestao/formatos.py`,
`app/ingestao/inspecionar.py`): geojsonseq, kml, dxf, filegdb.zip, xlsx — os 4 da fundação (shapefile.zip, gpkg,
geojson, csv) já são cobertos por `test_ingestao.py`. Portão: cada formato importa por upload e os atributos e a
geometria batem com o dado de origem (não só a contagem) — comparação feição a feição contra o `cobertura.geojson`
de referência (mesmo recorte que gerou os arquivos, `tests/dados/gerar.py`).

`_confirmar_com_retentativa`: a bancada roda ao lado de outras 7 trilhas que compartilham o MESMO schema de dado
`d_demo` (achado documentado em `laco/trilha_ambiente.sh`, seção c2: o produto ainda não separa `d_<slug>` por
ambiente) — o GRANT concorrente de `plat.camada_schema_garantir` esbarra em `tuple concurrently updated` de vez
em quando quando duas trilhas criam schema/tabela no mesmo instante. Não é bug do L6-02-o; repetir a carga uma
vez basta (mesma tolerância que o driver do worker já tem para deadlock)."""

from __future__ import annotations

import json

import pytest
from shapely.geometry import shape as shapely_shape

from tests.api.ingestao.conftest import GERADOS
from tests.api.test_rls import contexto, ids_por_slug

pytestmark = pytest.mark.skipif(not GERADOS.exists(), reason="rode `venv/bin/python tests/dados/gerar.py` antes")

_RACE_CONHECIDA = "tuple concurrently updated"


def _contexto_admin(con, ids: dict, slug: str = "demo"):
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")


def _tabela_de(cur, item_id: str) -> tuple[str, str]:
    cur.execute("SELECT dados->>'schema' AS schema, dados->>'tabela' AS tabela FROM plat.item WHERE id=%s::uuid",
                (item_id,))
    r = cur.fetchone()
    return r["schema"], r["tabela"]


def _importar_com_retentativa(ing, nome_arquivo: str, formato: str, tentativas: int = 3, **kw) -> tuple[str, dict]:
    """`ing.importar()` + `ing.confirmar()`; se a CARGA falhar pela corrida conhecida de schema entre trilhas
    (`_RACE_CONHECIDA`), a importação já foi para `falhou` e não é reenfileirável pelo mesmo id — refaz o
    upload inteiro do zero (só assim há uma importação nova em estado `proposta` para confirmar de novo)."""
    ultimo_final = None
    for _ in range(tentativas):
        importacao_id, insp = ing.importar(nome_arquivo, formato, **kw)
        final = ing.confirmar(importacao_id)
        if final.get("estado") == "concluida":
            return insp, final
        ultimo_final = final
        if _RACE_CONHECIDA not in (final.get("erro") or ""):
            return insp, final
    return insp, ultimo_final


def _linhas_geom_area(cur, schema: str, tabela: str) -> list[tuple[str, float]]:
    """[(name, área)] ordenado por fid — a "área" é o suficiente para achar geometria trocada/perdida sem exigir
    bit-a-bit (reprojeção/promoção Multi* mudam o WKT, não a forma)."""
    cur.execute(f'SELECT name, ST_Area(geom) AS area FROM "{schema}"."{tabela}" ORDER BY fid')
    return [(r["name"], float(r["area"] or 0)) for r in cur.fetchall()]


def _referencia() -> list[tuple[str | None, float]]:
    """As 10 feições de `cobertura.geojsonl` (o recorte NOMEADO — `name IS NOT NULL` — que alimentou geojsonseq,
    kml, dxf e filegdb.zip; `tests/dados/gerar.py::gerar_cobertura_nomeada`), como (name, área). Área em graus
    (WGS84/SIRGAS2000 — mesma unidade para este recorte pequeno); a comparação é de ORDEM DE GRANDEZA e
    presença, não de valor exato bit a bit."""
    linhas = (GERADOS / "cobertura.geojsonl").read_text(encoding="utf-8").splitlines()
    saida = []
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        f = json.loads(linha)
        geom = shapely_shape(f["geometry"])
        saida.append((f["properties"].get("name"), geom.area))
    return saida


def test_geojsonseq_importa_com_atributos_e_geometria(ingestor_a, conexao_plat_app):
    insp, final = _importar_com_retentativa(ingestor_a, "cobertura.geojsonl", "geojsonseq",
                                            content_type="application/x-ndjson")
    assert insp["estado"] == "proposta", insp
    assert insp["proposta"]["feicoes"] == 10
    assert insp["proposta"]["crs"]["srid"] == 4326
    assert not insp["proposta"]["perguntas"]
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 10

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        linhas = _linhas_geom_area(cur, schema, tabela)
    ref = _referencia()
    assert [n for n, _ in linhas] == [n for n, _ in ref]
    for (_, a1), (_, a2) in zip(linhas, ref, strict=True):
        assert a1 == pytest.approx(a2, rel=0.05) or (a1 == 0 and a2 == 0)


def test_kml_importa_atributos_extended_data(ingestor_a, conexao_plat_app):
    insp, final = _importar_com_retentativa(ingestor_a, "cobertura.kml", "kml",
                                            content_type="application/vnd.google-earth.kml+xml")
    assert insp["estado"] == "proposta", insp
    assert insp["proposta"]["feicoes"] == 10
    assert insp["proposta"]["crs"]["srid"] == 4326
    campos = {c["origem"] for c in insp["proposta"]["campos"]}
    # o LIBKML mapeia um campo chamado "name" para o elemento nativo <name>/<Name> do KML (não vira
    # ExtendedData) — "landuse" não colide com nada do formato e prova que ExtendedData sobrevive.
    assert "Name" in campos
    assert "landuse" in campos
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 10

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        cur.execute(f'SELECT name, ST_Area(geom) AS area FROM "{schema}"."{tabela}" ORDER BY fid')
        linhas = [(r["name"], float(r["area"] or 0)) for r in cur.fetchall()]
    ref = _referencia()
    assert [n for n, _ in linhas] == [n for n, _ in ref]


def test_dxf_importa_so_geometria_sem_atributo_arbitrario(ingestor_a, conexao_plat_app):
    """DXF não é falha nossa: o driver recusa campo arbitrário (medido com `ogr2ogr`). A proposta tem de mostrar
    só os campos REAIS do formato (Layer/SubClasses/Linetype/EntityHandle/Text), nunca fingir `name`/`landuse`;
    e tem de perguntar CRS (o formato não carrega nenhum, igual shapefile sem `.prj`)."""
    insp, final = _importar_com_retentativa(ingestor_a, "cobertura.dxf", "dxf")
    assert insp["estado"] == "proposta", insp
    assert insp["proposta"]["feicoes"] == 10
    assert "crs" in insp["proposta"]["perguntas"]
    campos = {c["origem"] for c in insp["proposta"]["campos"]}
    assert campos <= {"Layer", "PaperSpace", "SubClasses", "Linetype", "EntityHandle", "Text"}
    assert "name" not in campos and "landuse" not in campos

    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 10
    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        cur.execute(f'SELECT ST_Area(geom) AS a FROM "{schema}"."{tabela}" ORDER BY fid')
        areas = sorted(float(r["a"] or 0) for r in cur.fetchall())
    ref = sorted(a for _, a in _referencia())
    for a1, a2 in zip(areas, ref, strict=True):
        assert a1 == pytest.approx(a2, rel=0.05) or (a1 == 0 and a2 == 0)


def test_filegdb_zip_importa_com_atributos_e_geometria(ingestor_a, conexao_plat_app):
    insp, final = _importar_com_retentativa(ingestor_a, "cobertura_gdb.zip", "filegdb.zip",
                                            classe="camada_arquivo", content_type="application/zip")
    assert insp["estado"] == "proposta", insp
    assert insp["proposta"]["feicoes"] == 10
    assert insp["proposta"]["crs"]["srid"] == 4674  # FileGDB carrega SRS própria, sem perguntar
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 10

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        linhas = _linhas_geom_area(cur, schema, tabela)
    ref = _referencia()
    assert [n for n, _ in linhas] == [n for n, _ in ref]
    for (_, a1), (_, a2) in zip(linhas, ref, strict=True):
        assert a1 == pytest.approx(a2, rel=0.05) or (a1 == 0 and a2 == 0)


def test_xlsx_importa_pontos_por_latitude_longitude(ingestor_a, conexao_plat_app):
    insp, final = _importar_com_retentativa(
        ingestor_a, "lugares.xlsx", "xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert insp["estado"] == "proposta", insp
    assert insp["proposta"]["feicoes"] == 10
    assert insp["proposta"]["geometria"]["escolhida"] == "Point"
    assert insp["proposta"]["crs"]["sugestao"] == 4674
    assert final["estado"] == "concluida", final
    assert final["relatorio"]["feicoes_carregadas"] == 10

    ids = ids_por_slug(conexao_plat_app)
    _contexto_admin(conexao_plat_app, ids)
    with conexao_plat_app.cursor() as cur:
        schema, tabela = _tabela_de(cur, final["item_id"])
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}" WHERE geom IS NOT NULL')
        assert cur.fetchone()["n"] == 10
