"""Fixtures do ataque adversarial do grupo G3 (itens L0-04-* e L0-05-*). Reusa as fixtures da suíte de
ingestão (tests/api/ingestao/conftest.py) sem editá-las: este pacote só ACRESCENTA arquivos de ataque."""

from __future__ import annotations

import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

from tests.api.ingestao.conftest import *  # noqa: F401,F403 — Ingestor, ingestor_a, esperar_job, GERADOS

GERADOS = Path(__file__).resolve().parents[2] / "dados" / "gerados"
ATAQUE = GERADOS / "adv_g3"


def _ogr(*args: str) -> None:
    r = subprocess.run(["ogr2ogr", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.fixture(scope="session")
def arquivos_de_ataque() -> Path:
    """Gera os arquivos malformados/grandes do ataque (nenhum é baixado: tudo derivado do dado aberto que a
    própria suíte já gera em tests/dados/gerados/, ou escrito à mão)."""
    ATAQUE.mkdir(parents=True, exist_ok=True)
    base = GERADOS / "cobertura.geojson"
    assert base.exists(), "rode tests/dados/gerar.py antes"

    # a) GeoPackage com 3 camadas (portão do L0-04-b: 'GPKG com 3 camadas')
    tres = ATAQUE / "tres_camadas.gpkg"
    if not tres.exists():
        _ogr("-f", "GPKG", str(tres), str(base), "-nln", "camada_um")
        _ogr("-f", "GPKG", "-update", "-append", str(tres), str(base), "-nln", "camada_dois")
        _ogr("-f", "GPKG", "-update", "-append", str(tres), str(base), "-nln", "camada_tres")

    # b) CSV com 300 colunas e 0 linhas (refutação literal do L0-04-b)
    largo = ATAQUE / "largo_300_colunas.csv"
    if not largo.exists():
        largo.write_text(",".join(f"col_{i}" for i in range(300)) + "\n", encoding="utf-8")

    # c) GeoJSON com o membro `crs` legado de 31982 (refutação literal do L0-04-d)
    crs_legado = ATAQUE / "crs_legado_31982.geojson"
    if not crs_legado.exists():
        crs_legado.write_text(
            '{"type":"FeatureCollection",'
            '"crs":{"type":"name","properties":{"name":"urn:ogc:def:crs:EPSG::31982"}},'
            '"features":[{"type":"Feature","properties":{"a":1},'
            '"geometry":{"type":"Point","coordinates":[300000.0,7400000.0]}}]}',
            encoding="utf-8")

    # d) zip corrompido declarado como shapefile.zip (o conferidor levanta ZipSuspeito, não ConteudoNaoCorresponde)
    zip_ruim = ATAQUE / "zip_corrompido.zip"
    if not zip_ruim.exists():
        bons = (GERADOS / "cobertura_shp.zip").read_bytes()
        # mantém a assinatura PK do começo (o verificador de conteúdo declarado olha os primeiros bytes)
        # e destrói o diretório central no fim: zipfile.ZipFile levanta BadZipFile -> ZipSuspeito
        zip_ruim.write_bytes(bons[:len(bons) // 2])

    # e) zip com zip aninhado dentro (ZipSuspeito por outro motivo)
    zip_aninhado = ATAQUE / "zip_aninhado.zip"
    if not zip_aninhado.exists():
        with zipfile.ZipFile(zip_aninhado, "w") as z:
            z.writestr("dentro.zip", (GERADOS / "cobertura_shp.zip").read_bytes())

    # f) shapefile cujo .shp está truncado (GDAL abre e falha no meio)
    return ATAQUE


@pytest.fixture(scope="session")
def geojson_muitos_vertices(arquivos_de_ataque) -> Path:
    """Uma feição com 1.000.000 de vértices (o adversário do portão pede 10 milhões; ver o laudo para a
    fronteira: a 1 milhão o comportamento já é o que interessa medir, com 1/10 do disco e da RAM)."""
    alvo = ATAQUE / "um_milhao_de_vertices.geojson"
    if not alvo.exists():
        n = 1_000_000
        with alvo.open("w", encoding="utf-8") as f:
            f.write('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"a":1},'
                    '"geometry":{"type":"LineString","coordinates":[')
            for i in range(n):
                f.write(("," if i else "") + f"[-46.{500000 + (i % 400000):06d},-23.500001]")
            f.write("]}}]}")
    return alvo


@pytest.fixture
def con_pg_adv(env):
    """Conexão psycopg2 no contexto do inquilino demo (para ler plat.tenant.uso_bytes sob RLS)."""
    import psycopg2
    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import contexto, ids_por_slug

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
            adm = cur.fetchone()["usuario_id"]
        contexto(con, ids["demo"], usuario_id=adm, login="admin")
        yield con
    finally:
        con.rollback()
        con.close()
