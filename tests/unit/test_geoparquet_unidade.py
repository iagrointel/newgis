"""Testes de unidade do GeoParquet particionado (item L2-15-a-geoparquet-bucket-catalogo): montagem do SELECT
com colunas de partição, o conversor DuckDB em processo próprio (partição, selo de versão 1.1.0, bbox lido do
arquivo gerado) e a refutação do adversário (geometria mista, SRID 31982, tabela sem geometria, campo com
texto grande). Nenhum destes precisa de Postgres nem de Garage — só `ogr2ogr` (já usado pelo L0-04-h) e o
DuckDB local."""

from __future__ import annotations

import json
import os
import subprocess

import pytest
import referencing
from jsonschema import Draft7Validator

from app.geoparquet import duckdb_cli, motor

RAIZ_SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                          "app", "geoparquet", "geoparquet_1_1_schema.json")
GEOPARQUET_SCHEMA = json.load(open(RAIZ_SCHEMA, encoding="utf-8"))

# O schema oficial referencia `$ref` remoto (projjson do proj.org) para validar `columns[].crs`. Sem um
# registro LOCAL, o jsonschema busca esse `$ref` NA REDE a cada `.validate()` — funciona nesta máquina (tem
# saída), mas prenderia o teste à internet e ao ar do proj.org estar de pé. O CRS em si já é escrito pelo
# DuckDB/PROJ (não por este item); aqui só interessa que o NOSSO metadado (version/primary_column/columns/
# encoding/geometry_types) está certo, então o `$ref` do CRS é resolvido para um schema "aceita tudo" local.
_REGISTRO_OFFLINE = referencing.Registry().with_resource(
    "https://proj.org/schemas/v0.7/projjson.schema.json",
    referencing.Resource.from_contents({}, default_specification=referencing.jsonschema.DRAFT7),
)


def _validador():
    return Draft7Validator(GEOPARQUET_SCHEMA, registry=_REGISTRO_OFFLINE)


def _cur_falso():
    """Testes de unidade não passam `where` (sem parâmetro): o `mogrify` real do psycopg2 só entra em jogo
    quando há parâmetro a escapar, o que aqui é testado à parte (`where_ast` já tem suíte própria)."""
    class CursorFalso:
        def mogrify(self, sql, params):
            assert not params, "estes testes não usam where; params deveria vir vazio"
            return sql.encode()
    return CursorFalso()


# ---------------------------------------------------------------- montar_select
def test_montar_select_sem_particao():
    sql, colunas = motor.montar_select(
        _cur_falso(), schema="d_teste", tabela="c_1", campos=["nome", "uf"], coluna_geom="geom",
        where=None, srid_tabela=4674, colunas_brancas={"nome": '"nome"', "uf": '"uf"'}, particionar_por=None,
    )
    assert colunas is None
    assert 'FROM "d_teste"."c_1"' in sql and '"geom"' in sql and "WHERE" not in sql


def test_montar_select_particao_por_valor():
    sql, colunas = motor.montar_select(
        _cur_falso(), schema="d_teste", tabela="c_1", campos=["nome", "uf"], coluna_geom="geom",
        where=None, srid_tabela=4674, colunas_brancas={"nome": '"nome"', "uf": '"uf"'},
        particionar_por={"coluna": "uf", "grao": "valor"},
    )
    assert colunas == "uf"
    assert '"uf"' in sql


def test_montar_select_particao_ano_mes():
    sql, colunas = motor.montar_select(
        _cur_falso(), schema="d_teste", tabela="c_1", campos=["nome"], coluna_geom="geom", where=None,
        srid_tabela=4674, colunas_brancas={"nome": '"nome"', "data_evento": '"data_evento"'},
        particionar_por={"coluna": "data_evento", "grao": "ano_mes"},
    )
    assert colunas == "_geoparquet_ano,_geoparquet_mes"
    assert "to_char" in sql and "_geoparquet_ano" in sql and "_geoparquet_mes" in sql


def test_montar_select_coluna_particao_fora_da_lista_branca():
    with pytest.raises(motor.ErroGeoparquet):
        motor.montar_select(
            _cur_falso(), schema="d_teste", tabela="c_1", campos=["nome"], coluna_geom="geom", where=None,
            srid_tabela=4674, colunas_brancas={"nome": '"nome"'},
            particionar_por={"coluna": "segredo", "grao": "valor"},
        )


# ---------------------------------------------------------------- duckdb_cli: fixtures de GPKG
def _gpkg(tmp_path, features, nome="camada.geojson", saida="camada.gpkg"):
    caminho_geojson = tmp_path / nome
    caminho_geojson.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    caminho_gpkg = tmp_path / saida
    r = subprocess.run(["ogr2ogr", "-f", "GPKG", str(caminho_gpkg), str(caminho_geojson), "-nln", "dados"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return caminho_gpkg


def _ponto(i, uf):
    return {"type": "Feature", "properties": {"id": i, "uf": uf, "nome": f"item {i}"},
            "geometry": {"type": "Point", "coordinates": [-46.6 + (i % 10) * 0.01, -23.5 + (i // 10) * 0.01]}}


# ---------------------------------------------------------------- portão: partição por UF gera 27 arquivos
def test_particao_por_uf_gera_27_arquivos_e_geo_1_1_valido(tmp_path):
    ufs = ["SP", "RJ", "MG", "ES", "BA", "PE", "CE", "PA", "AM", "RS", "PR", "SC", "GO", "DF", "MT", "MS", "AL",
          "SE", "PB", "RN", "PI", "MA", "TO", "RO", "AC", "RR", "AP"]
    assert len(ufs) == 27
    feats = [_ponto(i, ufs[i % 27]) for i in range(27 * 20)]
    gpkg = _gpkg(tmp_path, feats)
    destino = tmp_path / "saida"
    manifesto = duckdb_cli.particionar(str(gpkg), str(destino), 512, "uf", 50_000)
    assert len(manifesto["arquivos"]) == 27, [a["particao"] for a in manifesto["arquivos"]]
    assert manifesto["linhas_total"] == 27 * 20
    assert {a["particao"]["uf"] for a in manifesto["arquivos"]} == set(ufs)
    for a in manifesto["arquivos"]:
        assert a["linhas"] == 20
        assert a["bbox"] is not None and len(a["bbox"]) == 4
        caminho = destino / a["caminho"]
        meta = _metadado_geo(caminho)
        _validador().validate(meta)
        assert meta["version"] == "1.1.0"


def test_particao_sem_coluna_gera_arquivo_unico(tmp_path):
    feats = [_ponto(i, "SP") for i in range(50)]
    gpkg = _gpkg(tmp_path, feats)
    destino = tmp_path / "saida"
    manifesto = duckdb_cli.particionar(str(gpkg), str(destino), 512, "-", 50_000)
    assert len(manifesto["arquivos"]) == 1
    assert manifesto["arquivos"][0]["caminho"] == "dados.parquet"
    assert manifesto["arquivos"][0]["particao"] == {}


def _metadado_geo(caminho) -> dict:
    import pyarrow.parquet as pq
    meta = pq.ParquetFile(str(caminho)).metadata.metadata or {}
    assert b"geo" in meta, "arquivo sem metadado geo (deveria ter coluna geom)"
    return json.loads(meta[b"geo"])


# ---------------------------------------------------------------- refutação do adversário
def test_tabela_sem_geometria_nao_tem_metadado_geo_e_conta_certo(tmp_path):
    """'tabela sem geometria': o item ainda assim conta (bbox = None, sem `geo` no rodapé)."""
    caminho_csv = tmp_path / "sem_geom.csv"
    caminho_csv.write_text("id,nome\n1,a\n2,b\n3,c\n", encoding="utf-8")
    gpkg = tmp_path / "sem_geom.gpkg"
    r = subprocess.run(["ogr2ogr", "-f", "GPKG", str(gpkg), str(caminho_csv), "-oo", "GEOM_POSSIBLE_NAMES=nao_ha",
                       "-nln", "dados"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    manifesto = duckdb_cli.particionar(str(gpkg), str(tmp_path / "saida2"), 512, "-", 50_000)
    assert manifesto["linhas_total"] == 3
    assert manifesto["arquivos"][0]["bbox"] is None
    caminho = (tmp_path / "saida2") / manifesto["arquivos"][0]["caminho"]
    import pyarrow.parquet as pq
    meta = pq.ParquetFile(str(caminho)).metadata.metadata
    assert not meta or b"geo" not in meta


def test_geometria_mista_e_srid_31982_nao_quebra_e_fica_valido(tmp_path):
    """'geometria mista': Point e LineString na mesma tabela; 'CRS 31982' (SIRGAS 2000 / UTM 22S)."""
    feats = [
        {"type": "Feature", "properties": {"id": 1}, "geometry": {"type": "Point", "coordinates": [700000, 7400000]}},
        {"type": "Feature", "properties": {"id": 2},
         "geometry": {"type": "LineString", "coordinates": [[700000, 7400000], [700100, 7400100]]}},
    ]
    caminho_geojson = tmp_path / "misto.geojson"
    caminho_geojson.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    gpkg = tmp_path / "misto.gpkg"
    r = subprocess.run(["ogr2ogr", "-f", "GPKG", str(gpkg), str(caminho_geojson), "-a_srs", "EPSG:31982",
                       "-nlt", "GEOMETRY", "-nln", "dados"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    manifesto = duckdb_cli.particionar(str(gpkg), str(tmp_path / "saida3"), 512, "-", 50_000)
    assert manifesto["linhas_total"] == 2
    caminho = (tmp_path / "saida3") / manifesto["arquivos"][0]["caminho"]
    meta = _metadado_geo(caminho)
    _validador().validate(meta)
    assert set(meta["columns"]["geom"]["geometry_types"]) >= {"Point", "LineString"}


def test_campo_com_texto_grande_nao_quebra(tmp_path):
    """'campo com 10 MB de texto': o conversor não trava nem trunca. CSV, não GeoJSON: MEDIDO em 07/09/2026
    que o parser de GeoJSON do GDAL 3.8.4 falha ("Too many characters in number") num valor de string de
    10 MB — limitação do formato de ENTRADA do teste, não deste módulo. O driver CSV também tem teto: medido
    por busca binária que uma LINHA de ~9,9-10.000.000 caracteres já falha ("Maximum number of characters
    allowed reached"); 9 MB de campo (linha bem menor que o teto) passa e é o que este teste usa — a prova
    que importa (DuckDB/Parquet não trunca um campo grande) não depende de bater exatamente 10 MB de CSV."""
    caminho_csv = tmp_path / "grande.csv"
    texto_grande = "x" * (9 * 1024 * 1024)
    with open(caminho_csv, "w", encoding="utf-8") as f:
        f.write("id,nota\n")
        f.write(f"1,{texto_grande}\n")
    gpkg = tmp_path / "grande.gpkg"
    r = subprocess.run(["ogr2ogr", "-f", "GPKG", str(gpkg), str(caminho_csv), "-oo", "GEOM_POSSIBLE_NAMES=nao_ha",
                       "-nln", "dados"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    manifesto = duckdb_cli.particionar(str(gpkg), str(tmp_path / "saida4"), 512, "-", 50_000)
    assert manifesto["linhas_total"] == 1
    caminho = (tmp_path / "saida4") / manifesto["arquivos"][0]["caminho"]
    import pyarrow.parquet as pq
    tabela = pq.read_table(str(caminho))
    assert len(tabela.column("nota")[0].as_py()) == 9 * 1024 * 1024


# ---------------------------------------------------------------- selo de versão: segurança da troca binária
def test_selar_1_1_0_so_mexe_com_ocorrencia_unica(tmp_path):
    caminho = tmp_path / "a.bin"
    caminho.write_bytes(b'antes {"version":"1.0.0","x":1} depois')
    duckdb_cli._selar_1_1_0(str(caminho))
    assert caminho.read_bytes() == b'antes {"version":"1.1.0","x":1} depois'

    caminho2 = tmp_path / "b.bin"
    caminho2.write_bytes(b'{"version":"1.0.0"} ... {"version":"1.0.0"}')
    with pytest.raises(RuntimeError):
        duckdb_cli._selar_1_1_0(str(caminho2))

    caminho3 = tmp_path / "c.bin"
    caminho3.write_bytes(b"sem nada disso aqui")
    duckdb_cli._selar_1_1_0(str(caminho3))  # não faz nada, não levanta
    assert caminho3.read_bytes() == b"sem nada disso aqui"
