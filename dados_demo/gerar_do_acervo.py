"""Gerador dos arquivos do conjunto de demonstração (item L0-13-dado-demonstracao).

RODA SÓ NA CASA, uma vez, com acesso ao banco `iagro_sat` (as tabelas do acervo da iAgroSat, que já
guardam as bases públicas do IBGE, do DNIT, da ANA e do INMET). O resultado — os arquivos em
`dados_demo/arquivos/` — é COMITADO no repositório, e é ele que o instalador semeia: nenhuma
instalação de cliente executa este script nem baixa nada da rede.

Uso (na casa):  venv/bin/python dados_demo/gerar_do_acervo.py

Cada arquivo gerado tem uma linha em `dados_demo/catalogo.json` (fonte, órgão, endereço, licença,
data de acesso, inquilino de destino) e uma linha em `docs/DADO_DEMO.md`. O catálogo é a fonte de
verdade: `scripts/semear_dado_demo.py` semeia a partir dele e `tests/api/test_dado_demo.py` confere.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "dados_demo" / "arquivos"
TMP = Path("/tmp/plat_demo_t13")
BANCO = "PG:dbname=iagro_sat"
DATA_ACESSO = "2026-09-06"

# licenças: texto conferido na fonte, no mesmo vocabulário que a casa já usa no catálogo de camadas.
LIC_IBGE = "IBGE, dado aberto (o FTP declara apenas que os arquivos disponíveis são públicos)"
LIC_DNIT = "DNIT, dado público do VGeo; licença não declarada na fonte"
LIC_ANA = "ANA, dado aberto; licença não declarada na fonte (campo licenseInfo nulo no portal, conferido em 06/09/2026)"
LIC_INMET = "INMET, dado aberto; licença não declarada na fonte"
LIC_CASA = "CC0 1.0 (arquivo desenhado pela casa só para demonstração; nenhum dado de terceiro dentro)"


def _ogr(*args: str, como_postgres: bool = True) -> None:
    argv = ["ogr2ogr", *args]
    if como_postgres:
        argv = ["sudo", "-u", "postgres", *argv]
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ogr2ogr falhou: {' '.join(args)}\n{r.stderr}")


def _zip_shapefile(base: Path, destino_zip: Path) -> None:
    membros = sorted(base.parent.glob(base.name + ".*"))
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for m in membros:
            zf.write(m, m.name)


SQL_MUNICIPIOS = (
    "SELECT cd_ibge AS cd_mun, nm AS nome, cd_uf, "
    "ST_Multi(ST_SimplifyPreserveTopology(geom, 0.002))::geometry(MultiPolygon,4326) AS geom "
    "FROM tribuna_serving.municipio_geo WHERE cd_uf IN (%s) ORDER BY cd_ibge"
)
SQL_PONTOS = (
    "SELECT cd_ibge AS cd_mun, nm AS nome, cd_uf, "
    "ST_PointOnSurface(geom)::geometry(Point,4326) AS geom "
    "FROM tribuna_serving.municipio_geo WHERE cd_uf IN (%s) ORDER BY cd_ibge"
)
SQL_RODOVIAS = (
    "SELECT codigo_br, unidade_federacao AS uf, sigla_tipo_trecho, local_inicio, local_fim, "
    "quilometragem_inicio AS km_ini, quilometragem_fim AS km_fim, extensao, superficie_federal, "
    "versao_snv, ST_Multi(ST_SimplifyPreserveTopology(geom, 0.0002))::geometry(MultiLineString,4674) AS geom "
    "FROM public.amc_dnit_snv_rodovias WHERE unidade_federacao = '%s' ORDER BY codigo_br"
)
SQL_HIDRO = (
    "SELECT cotrecho, cobacia, nocomp AS nome, nucomptrec AS comp_km, nustrahler, geom FROM ("
    "  SELECT cotrecho, cobacia, coalesce(noriocomp, nogenerico) AS nocomp, nucomptrec, nustrahler,"
    "         ST_Multi(ST_SimplifyPreserveTopology(geom, 0.0002))::geometry(MultiLineString,4674) AS geom"
    "  FROM public.amc_bho_trechos_2017 WHERE cobacia LIKE '4668%%'"
    ") t ORDER BY cotrecho"
)
SQL_ESTACOES = (
    "SELECT cd_estacao, nome, uf, situacao, tp_estacao, lat AS latitude, lon AS longitude "
    "FROM public.inmet_stations WHERE uf IN (%s) AND lat IS NOT NULL ORDER BY cd_estacao"
)


def gerar_camadas() -> None:
    TMP.mkdir(exist_ok=True)
    for f in TMP.iterdir():
        if f.is_file():
            f.unlink()

    # 1. limites municipais de dois estados (AP=16, RR=14), shapefile em zip
    _ogr("-f", "ESRI Shapefile", str(TMP / "municipios_ap_rr.shp"), BANCO, "-sql",
         SQL_MUNICIPIOS % "'16','14'", "-nln", "municipios_ap_rr", "-lco", "ENCODING=UTF-8")
    _zip_shapefile(TMP / "municipios_ap_rr", DESTINO / "municipios_ap_rr.zip")

    # 2. ponto representativo de cada município (point-on-surface do próprio limite)
    _ogr("-f", "GeoJSON", str(TMP / "pontos_municipais_ap_rr.geojson"), BANCO, "-sql",
         SQL_PONTOS % "'16','14'", "-nln", "pontos_municipais_ap_rr")
    shutil.copyfile(TMP / "pontos_municipais_ap_rr.geojson", DESTINO / "pontos_municipais_ap_rr.geojson")

    # 3. rodovias federais de um estado (RR)
    _ogr("-f", "GeoJSON", str(TMP / "rodovias_federais_rr.geojson"), BANCO, "-sql",
         SQL_RODOVIAS % "RR", "-nln", "rodovias_federais_rr")
    shutil.copyfile(TMP / "rodovias_federais_rr.geojson", DESTINO / "rodovias_federais_rr.geojson")

    # 4. hidrografia de uma bacia (BHO 2017, otto-bacia 4668)
    _ogr("-f", "GeoJSON", str(TMP / "hidrografia_bacia_4668.geojson"), BANCO, "-sql", SQL_HIDRO,
         "-nln", "hidrografia_bacia_4668")
    shutil.copyfile(TMP / "hidrografia_bacia_4668.geojson", DESTINO / "hidrografia_bacia_4668.geojson")

    # 5. estações meteorológicas (CSV com latitude/longitude), Norte
    _ogr("-f", "CSV", str(TMP / "estacoes_inmet_norte.csv"), BANCO, "-sql",
         SQL_ESTACOES % "'AC','AM','AP','PA','RO','RR','TO'", "-nln", "estacoes_inmet_norte")
    shutil.copyfile(TMP / "estacoes_inmet_norte.csv", DESTINO / "estacoes_inmet_norte.csv")

    # 6. GeoPackage com três camadas (as três acima, no mesmo arquivo)
    gpkg = DESTINO / "demonstracao_3_camadas.gpkg"
    gpkg.unlink(missing_ok=True)
    _ogr("-f", "GPKG", str(gpkg), str(DESTINO / "pontos_municipais_ap_rr.geojson"),
         "-nln", "pontos_municipais", como_postgres=False)
    _ogr("-f", "GPKG", "-update", str(gpkg), str(DESTINO / "rodovias_federais_rr.geojson"),
         "-nln", "rodovias_federais", como_postgres=False)
    _ogr("-f", "GPKG", "-update", str(gpkg), str(DESTINO / "hidrografia_bacia_4668.geojson"),
         "-nln", "hidrografia", como_postgres=False)

    # 7. planilha XLSX das mesmas estações (driver XLSX do GDAL, sem dependência nova)
    xlsx = DESTINO / "estacoes_inmet_norte.xlsx"
    xlsx.unlink(missing_ok=True)
    _ogr("-f", "XLSX", str(xlsx), str(DESTINO / "estacoes_inmet_norte.csv"), "-nln", "estacoes",
         como_postgres=False)

    # 8. segundo inquilino (demo2): conjunto DIFERENTE — Acre
    _ogr("-f", "ESRI Shapefile", str(TMP / "municipios_ac.shp"), BANCO, "-sql",
         SQL_MUNICIPIOS % "'12'", "-nln", "municipios_ac", "-lco", "ENCODING=UTF-8")
    _zip_shapefile(TMP / "municipios_ac", DESTINO / "municipios_ac.zip")
    _ogr("-f", "GeoJSON", str(TMP / "rodovias_federais_ac.geojson"), BANCO, "-sql",
         SQL_RODOVIAS % "AC", "-nln", "rodovias_federais_ac")
    shutil.copyfile(TMP / "rodovias_federais_ac.geojson", DESTINO / "rodovias_federais_ac.geojson")
    _ogr("-f", "CSV", str(TMP / "estacoes_inmet_centro_oeste.csv"), BANCO, "-sql",
         SQL_ESTACOES % "'DF','GO','MT','MS'", "-nln", "estacoes_inmet_centro_oeste")
    shutil.copyfile(TMP / "estacoes_inmet_centro_oeste.csv", DESTINO / "estacoes_inmet_centro_oeste.csv")


def gerar_dxf() -> None:
    """Desenho de exemplo da casa: uma gleba fictícia de 200 m x 150 m com um galpão e a via de acesso,
    em SIRGAS 2000 / UTM 21S (EPSG:31981), a zona de Roraima. Nenhum dado de terceiro, nenhum cliente."""
    x0, y0 = 700_000.0, 300_000.0
    gleba = [(x0, y0), (x0 + 200, y0), (x0 + 200, y0 + 150), (x0, y0 + 150), (x0, y0)]
    galpao = [(x0 + 40, y0 + 40), (x0 + 140, y0 + 40), (x0 + 140, y0 + 100), (x0 + 40, y0 + 100), (x0 + 40, y0 + 40)]
    via = [(x0 - 60, y0 + 70), (x0, y0 + 70)]
    colecao = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"camada": "gleba", "descricao": "perímetro da gleba"},
             "geometry": {"type": "LineString", "coordinates": [list(p) for p in gleba]}},
            {"type": "Feature", "properties": {"camada": "edificacao", "descricao": "galpão de exemplo"},
             "geometry": {"type": "LineString", "coordinates": [list(p) for p in galpao]}},
            {"type": "Feature", "properties": {"camada": "acesso", "descricao": "via de acesso"},
             "geometry": {"type": "LineString", "coordinates": [list(p) for p in via]}},
        ],
    }
    origem = TMP / "planta_exemplo.geojson"
    origem.write_text(json.dumps(colecao), encoding="utf-8")
    destino = DESTINO / "planta_exemplo.dxf"
    destino.unlink(missing_ok=True)
    _ogr("-f", "DXF", str(destino), str(origem), "-a_srs", "EPSG:31981", como_postgres=False)


def escrever_catalogo() -> None:
    itens = [
        dict(arquivo="municipios_ap_rr.zip", inquilino="demo", formato="shapefile.zip", ingerir=True,
             titulo="Limites municipais do Amapá e de Roraima",
             resumo="Malha municipal do IBGE recortada em dois estados e simplificada para 0,002 grau.",
             tags=["ibge", "limites", "municipio"], categoria="Limites administrativos",
             fonte="IBGE, malha municipal", orgao="IBGE",
             url="https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/",
             licenca=LIC_IBGE, data_acesso=DATA_ACESSO),
        dict(arquivo="pontos_municipais_ap_rr.geojson", inquilino="demo", formato="geojson", ingerir=True,
             titulo="Ponto representativo dos municípios do Amapá e de Roraima",
             resumo="Um ponto por município, obtido por ST_PointOnSurface do próprio limite municipal do IBGE. "
                    "Não é a sede municipal oficial.",
             tags=["ibge", "ponto", "municipio"], categoria="Limites administrativos",
             fonte="IBGE, malha municipal (ponto derivado pela casa)", orgao="IBGE",
             url="https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/",
             licenca=LIC_IBGE, data_acesso=DATA_ACESSO),
        dict(arquivo="rodovias_federais_rr.geojson", inquilino="demo", formato="geojson", ingerir=True,
             titulo="Rodovias federais de Roraima",
             resumo="Trechos do Sistema Nacional de Viação (SNV) do DNIT no estado de Roraima.",
             tags=["dnit", "rodovia", "transporte"], categoria="Transporte",
             fonte="DNIT, SNV (rodovias federais)", orgao="DNIT",
             url="https://servicos.dnit.gov.br/vgeo/", licenca=LIC_DNIT, data_acesso=DATA_ACESSO),
        dict(arquivo="hidrografia_bacia_4668.geojson", inquilino="demo", formato="geojson", ingerir=True,
             titulo="Hidrografia da otto-bacia 4668",
             resumo="Trechos de drenagem da Base Hidrográfica Ottocodificada (BHO 2017) de uma única otto-bacia.",
             tags=["ana", "hidrografia", "bacia"], categoria="Água",
             fonte="ANA, Base Hidrográfica Ottocodificada (BHO 2017)", orgao="ANA",
             url="https://dadosabertos.ana.gov.br/", licenca=LIC_ANA, data_acesso=DATA_ACESSO),
        dict(arquivo="estacoes_inmet_norte.csv", inquilino="demo", formato="csv", ingerir=True,
             titulo="Estações meteorológicas do INMET na região Norte",
             resumo="Cadastro de estações automáticas e convencionais do INMET, com latitude e longitude.",
             tags=["inmet", "estacao", "clima"], categoria="Clima",
             fonte="INMET, cadastro de estações", orgao="INMET",
             url="https://portal.inmet.gov.br/dadoshistoricos", licenca=LIC_INMET, data_acesso=DATA_ACESSO),
        dict(arquivo="demonstracao_3_camadas.gpkg", inquilino="demo", formato="gpkg", ingerir=True,
             titulo="GeoPackage de demonstração com três camadas",
             resumo="Um arquivo com pontos municipais, rodovias federais e hidrografia. A ingestão desta "
                    "versão carrega a PRIMEIRA camada do arquivo (escolha de camada é lacuna do L0-04-d).",
             tags=["gpkg", "demonstracao"], categoria="Demonstração",
             fonte="IBGE, DNIT e ANA (mesmas camadas acima, reunidas pela casa)", orgao="IBGE/DNIT/ANA",
             url="https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/",
             licenca=f"{LIC_IBGE}; {LIC_DNIT}; {LIC_ANA}", data_acesso=DATA_ACESSO),
        dict(arquivo="estacoes_inmet_norte.xlsx", inquilino="demo", formato="xlsx", ingerir=False,
             titulo="Planilha das estações do INMET na região Norte",
             resumo="A mesma tabela do CSV em XLSX. Fica no catálogo como arquivo: a ingestão de XLSX é "
                    "lacuna do L0-04-d.",
             tags=["inmet", "planilha"], categoria="Clima",
             fonte="INMET, cadastro de estações (convertido pela casa)", orgao="INMET",
             url="https://portal.inmet.gov.br/dadoshistoricos", licenca=LIC_INMET, data_acesso=DATA_ACESSO),
        dict(arquivo="planta_exemplo.dxf", inquilino="demo", formato="dxf", ingerir=False,
             titulo="Planta de exemplo em DXF",
             resumo="Gleba fictícia de 200 m por 150 m com galpão e via de acesso, em SIRGAS 2000 / UTM 21S. "
                    "Desenhada pela casa. Fica no catálogo como arquivo: a ingestão de DXF é lacuna do L0-04-d.",
             tags=["dxf", "desenho"], categoria="Demonstração",
             fonte="desenho da casa (dados_demo/gerar_do_acervo.py)", orgao="iAgroSat",
             url="https://iagrointel.com/", licenca=LIC_CASA, data_acesso=DATA_ACESSO),
        dict(arquivo="municipios_ac.zip", inquilino="demo2", formato="shapefile.zip", ingerir=True,
             titulo="Limites municipais do Acre",
             resumo="Malha municipal do IBGE recortada no Acre e simplificada para 0,002 grau.",
             tags=["ibge", "limites", "municipio"], categoria="Limites administrativos",
             fonte="IBGE, malha municipal", orgao="IBGE",
             url="https://ftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/",
             licenca=LIC_IBGE, data_acesso=DATA_ACESSO),
        dict(arquivo="rodovias_federais_ac.geojson", inquilino="demo2", formato="geojson", ingerir=True,
             titulo="Rodovias federais do Acre",
             resumo="Trechos do Sistema Nacional de Viação (SNV) do DNIT no estado do Acre.",
             tags=["dnit", "rodovia", "transporte"], categoria="Transporte",
             fonte="DNIT, SNV (rodovias federais)", orgao="DNIT",
             url="https://servicos.dnit.gov.br/vgeo/", licenca=LIC_DNIT, data_acesso=DATA_ACESSO),
        dict(arquivo="estacoes_inmet_centro_oeste.csv", inquilino="demo2", formato="csv", ingerir=True,
             titulo="Estações meteorológicas do INMET na região Centro-Oeste",
             resumo="Cadastro de estações automáticas e convencionais do INMET, com latitude e longitude.",
             tags=["inmet", "estacao", "clima"], categoria="Clima",
             fonte="INMET, cadastro de estações", orgao="INMET",
             url="https://portal.inmet.gov.br/dadoshistoricos", licenca=LIC_INMET, data_acesso=DATA_ACESSO),
    ]
    for it in itens:
        caminho = DESTINO / it["arquivo"]
        dados = caminho.read_bytes()
        it["bytes"] = len(dados)
        it["sha256"] = hashlib.sha256(dados).hexdigest()
    catalogo = {
        "gerado_por": "dados_demo/gerar_do_acervo.py",
        "data_acesso": DATA_ACESSO,
        "observacao": "Arquivos comitados no repositório; o instalador semeia a partir daqui, sem rede.",
        "itens": itens,
    }
    (RAIZ / "dados_demo" / "catalogo.json").write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


CABECALHO = """# Dado de demonstração (item L0-13-dado-demonstracao)

Conjunto pequeno e aberto que o instalador semeia nos inquilinos de demonstração `demo` e `demo2`,
para que a plataforma nunca precise de dado de cliente para ser mostrada, testada ou fotografada.

- Os arquivos ficam em `dados_demo/arquivos/`, comitados no repositório (nenhuma instalação baixa
  nada da rede). Tamanho total medido: **{tamanho}**.
- `dados_demo/catalogo.json` é a fonte de verdade (arquivo, inquilino, formato, título, resumo,
  tags, categoria, fonte, órgão, endereço, licença, data de acesso, bytes e sha256).
- `scripts/semear_dado_demo.py` semeia pela PRÓPRIA API: envia o arquivo, registra o item de
  arquivo, cria a importação e confirma a proposta. Não existe caminho paralelo de carga.
- Este documento é gerado por `dados_demo/gerar_do_acervo.py --so-doc`; não edite à mão.
- Nenhum arquivo tem nome de pessoa, CPF, nome de empresa privada, nome de cliente, de parceiro ou
  de piloto. O que existe de nome próprio é topônimo oficial do IBGE (município, rio, rodovia).
- `demo` e `demo2` recebem conjuntos DIFERENTES: o que está num não aparece no outro. É assim que se
  vê na tela que um inquilino não enxerga o dado do outro.

## Cada arquivo, com fonte, endereço, licença e data de acesso

"""


def escrever_doc() -> None:
    catalogo = json.loads((RAIZ / "dados_demo" / "catalogo.json").read_text(encoding="utf-8"))
    total = sum(it["bytes"] for it in catalogo["itens"])
    linhas = [CABECALHO.format(tamanho=f"{total / 1e6:.2f} MB em {len(catalogo['itens'])} arquivos")]
    for inquilino in ("demo", "demo2"):
        linhas.append(f"### Inquilino `{inquilino}`\n")
        for it in catalogo["itens"]:
            if it["inquilino"] != inquilino:
                continue
            entra = ("carregado como camada pela ingestão" if it["ingerir"]
                     else "fica no catálogo como arquivo (formato ainda não ingerido: lacuna do L0-04-d)")
            linhas.append(
                f"#### `{it['arquivo']}`\n\n"
                f"- Título no catálogo: {it['titulo']}\n"
                f"- Fonte: {it['fonte']}\n"
                f"- Órgão: {it['orgao']}\n"
                f"- Endereço: {it['url']}\n"
                f"- Licença: {it['licenca']}\n"
                f"- Data de acesso: {it['data_acesso']}\n"
                f"- Formato: {it['formato']} · {it['bytes']} bytes · sha256 `{it['sha256']}`\n"
                f"- Uso: {entra}\n"
            )
    linhas.append(
        "## O que a semeadura cria além dos arquivos\n\n"
        "No inquilino `demo`: as categorias do catálogo, dois grupos de demonstração, o primeiro item\n"
        "compartilhado com um desses grupos, um link de compartilhamento e um item na lixeira\n"
        "(`Planta de exemplo (versão retirada do catálogo)`).\n"
    )
    (RAIZ / "docs" / "DADO_DEMO.md").write_text("\n".join(linhas), encoding="utf-8")


def main() -> None:
    if "--so-doc" in sys.argv:
        escrever_doc()
        print(f"{RAIZ / 'docs' / 'DADO_DEMO.md'} reescrito do catálogo")
        return
    DESTINO.mkdir(parents=True, exist_ok=True)
    gerar_camadas()
    gerar_dxf()
    escrever_catalogo()
    escrever_doc()
    total = sum(f.stat().st_size for f in DESTINO.iterdir())
    print(f"{len(list(DESTINO.iterdir()))} arquivos, {total / 1e6:.2f} MB em {DESTINO}")


if __name__ == "__main__":
    main()
