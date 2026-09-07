"""Esquema do tipo `mapa_base` (item L2-01-e-mapas-base): lido direto da migração (fonte única — nenhuma cópia
Python do JSON Schema, para nunca haver duas versões desalinhadas), validado com o mesmo motor que
`app.catalogo.tipos.validar` usa em produção (jsonschema Draft202012Validator). Não toca o banco: é isto que
faz este teste "unit", não "api" — tipos.validar exigiria a tabela plat.tipo_item populada."""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
MIGRACAO = ROOT / "db" / "migracoes" / "20260907T1649_mapa_base.sql"


def _esquema() -> dict:
    sql = MIGRACAO.read_text(encoding="utf-8")
    padrao = (
        r"'(\{\"\$schema\":\"https://json-schema\.org/draft/2020-12/schema\".*?\})'::jsonb,"
        r"\n\s*1, 'mapa_base'"
    )
    m = re.search(padrao, sql, re.S)
    assert m, "esquema de mapa_base não encontrado na migração (regex desalinhou do arquivo)"
    return json.loads(m.group(1))


@pytest.fixture(scope="module")
def validador():
    return Draft202012Validator(_esquema(), format_checker=Draft202012Validator.FORMAT_CHECKER)


def _erros(validador, dados):
    return [e.message for e in validador.iter_errors(dados)]


# ---------------------------------------------------------------- casos válidos (as 4 fontes de semear.py)
@pytest.mark.parametrize("dados", [
    {"tipo": "pmtiles", "estilo": "escuro", "url": "/static/dados/basemap/guarulhos.pmtiles",
     "zoom_min": 0, "zoom_max": 16, "ordem": 0, "padrao": True},
    {"tipo": "osm_raster_proxy", "url": "/api/mapas-base/osm/{z}/{x}/{y}.png",
     "zoom_min": 0, "zoom_max": 19, "ordem": 1},
    {"tipo": "satelite_titiler", "url": "https://titiler.exemplo/cog/tiles/{z}/{x}/{y}.png?url=s3://demo/x.tif",
     "zoom_min": 8, "zoom_max": 14, "ordem": 2},
    {"tipo": "nenhum", "ordem": 3},
])
def test_fontes_padrao_validam(validador, dados):
    assert _erros(validador, dados) == [], _erros(validador, dados)


# ---------------------------------------------------------------- refutação: SSRF pelo esquema
@pytest.mark.parametrize("url_maliciosa", [
    "http://169.254.169.254/{z}/{x}/{y}.png",       # metadado de nuvem
    "http://tile.evil.example/{z}/{x}/{y}.png",     # host fora da lista
    "/api/mapas-base/osm/{z}/{x}/{y}.png/../../x",  # tentativa de escapar do caminho fixo
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",  # até o host OFICIAL: só o proxy é aceito, nunca direto
])
def test_osm_raster_proxy_so_aceita_o_proprio_caminho_do_proxy(validador, url_maliciosa):
    """Refutação do item: 'adversário tenta usar o proxy OSM como proxy aberto (host arbitrário)'. Como o
    esquema fixa `url` com `const`, não existe combinação de host que passe — SSRF é impossível já na
    criação do item, antes de qualquer código de rede rodar."""
    dados = {"tipo": "osm_raster_proxy", "url": url_maliciosa, "zoom_min": 0, "zoom_max": 19, "ordem": 1}
    assert _erros(validador, dados) != []


def test_nenhum_e_o_unico_tipo_sem_url_obrigatoria(validador):
    assert _erros(validador, {"tipo": "nenhum", "ordem": 0}) == []
    for tipo in ("pmtiles", "osm_raster_proxy", "satelite_titiler"):
        assert _erros(validador, {"tipo": tipo, "ordem": 0}) != [], tipo


def test_pmtiles_url_tem_de_ser_do_caminho_static_dados_basemap(validador):
    ok = {"tipo": "pmtiles", "url": "/static/dados/basemap/x.pmtiles", "zoom_min": 0, "zoom_max": 10, "ordem": 0}
    assert _erros(validador, ok) == []
    ruim = dict(ok, url="/static/outro/x.pmtiles")
    assert _erros(validador, ruim) != []
    ruim2 = dict(ok, url="https://cdn.terceiro.com/x.pmtiles")
    assert _erros(validador, ruim2) != []


def test_satelite_titiler_exige_os_tres_marcadores(validador):
    base = {"tipo": "satelite_titiler", "zoom_min": 8, "zoom_max": 14, "ordem": 2}
    assert _erros(validador, dict(base, url="https://x/cog/{z}/{x}/{y}.png")) == []
    for url_incompleta in ("https://x/cog/{x}/{y}.png", "https://x/cog/fixo.png", "ftp://x/{z}/{x}/{y}.png"):
        assert _erros(validador, dict(base, url=url_incompleta)) != [], url_incompleta


def test_tipo_fora_do_enum_e_campo_extra_recusados(validador):
    assert _erros(validador, {"tipo": "wms", "ordem": 0}) != []
    ok = {"tipo": "nenhum", "ordem": 0, "campo_nao_previsto": 1}
    assert _erros(validador, ok) != []  # additionalProperties: false
