"""Exportação vetorial (item L6-02-o-importacao-exportacao-formatos): a mesma tabela PostGIS que
`app/ingestao/carregar.py` cria vira arquivo de novo, no formato que o pedido escolher, com mapeamento de campos
(renomear/excluir) e de CRS (reprojeção). Dois jobs:

- `ingestao.exportar_camada`: exporta UM item `camada_vetorial` para um objeto do armazenamento (classe
  `exportacao`), nos formatos que o GDAL desta máquina ESCREVE de verdade (MEDIDO nesta passagem, `ogr --formats`
  + teste de ida e volta em `tests/api/ingestao/test_exportar.py`): gpkg, shapefile.zip, geojson, geojsonseq,
  kml, dxf, csv, xlsx, filegdb.zip, mvt, pmtiles. MSSQLSpatial e Apache Parquet ficam de fora: MSSQLSpatial
  porque exigiria guardar credencial de servidor de terceiro sem um cofre para isso (`app/conexao/` cobre só
  leitura de serviço geográfico, não escrita em banco externo — decisão registrada no handoff, não esquecimento)
  e Parquet porque o driver nem existe no GDAL desta instalação (nunca prometer os dois).

- `ingestao.exportar_inquilino`: escrow do item L0-06 — todas as camadas do inquilino que chama num só GeoPackage
  (uma camada por layer) mais um manifesto JSON com o metadado de catálogo de cada uma (procedência,
  estatísticas, campos). Isolamento: cada inquilino tem seu próprio schema `d_<slug>` e a consulta a
  `plat.item` roda sob RLS da sessão do job (`ContextoJob._ctx`, mesma tenant do job) — nunca lista nem lê
  tabela de outro inquilino; teste cruzado em `tests/api/ingestao/test_exportar.py::test_isolamento_...`.

Limitação por formato (medida com `ogr2ogr`, não é bug nosso — documentada em `docs/PARIDADE.md`):
Shapefile trunca nome de campo em 10 caracteres (aviso de truncamento obrigatório, é a refutação do item); DXF só
aceita um punhado fixo de campos (Layer/SubClasses/Linetype/EntityHandle/Text) e recusa qualquer atributo
arbitrário (`ERROR 1: DXF layer does not support arbitrary field creation`, retorno 0 mesmo assim — não é falha
de job, é aviso); XLSX não tem geometria nativa (`ogrinfo --format XLSX`: "No support for geometries") — pontos
saem como colunas latitude/longitude reimportáveis pelo `_preparar_xlsx`, geometria não pontual sai só como texto
WKT de referência (não é reimportável automaticamente, dito no aviso); KML/GeoJSON/GeoJSONSeq forçam CRS 4326
(WGS84) na saída porque o formato não admite outro; MVT/PMTiles forçam EPSG:3857 (tiling de web mercator) e são
LOSSY por natureza do tile (quantização de coordenada — ver nota em `_estrategia_mvt/_estrategia_pmtiles`)."""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field

from app import objetos
from app.ingestao.carregar import _pg_conninfo
from app.jobs.registro import FalhaDefinitiva, tarefa

FORMATOS_EXPORTACAO = (
    "gpkg", "shapefile.zip", "geojson", "geojsonseq", "kml", "dxf", "csv", "xlsx", "filegdb.zip", "mvt", "pmtiles",
)
# formatos que não suportam campo arbitrário: avisos textuais que `ogr2ogr` imprime no stderr quando descarta
# um campo — usados para ACHAR e devolver o aviso de truncamento/perda (a refutação do item)
_PISTA_TRUNCAMENTO = "Normalized/laundered field name"
_PISTA_CAMPO_RECUSADO = "does not support arbitrary field creation"
_PISTA_TIPO_MISCONVERSAO = "does not natively support"

MVT_MAXZOOM_PADRAO = 16
PMTILES_MAXZOOM_PADRAO = 16


class ExportarCamadaParametros(BaseModel):
    item_id: uuid.UUID
    formato: str = Field(pattern="^(" + "|".join(FORMATOS_EXPORTACAO) + ")$")
    crs_srid: int | None = None
    campos: list[dict] | None = None  # [{"origem": "<nome interno>", "destino": "<novo nome>", "incluir": bool}]


class ExportarInquilinoParametros(BaseModel):
    formato: str = Field(default="gpkg+json", pattern="^gpkg\\+json$")


def _mapa_campos(campos_pedido: list[dict] | None) -> dict[str, dict]:
    return {c["origem"]: c for c in (campos_pedido or []) if c.get("origem")}


def _colunas_exportacao(campos_catalogo: list[dict], campos_pedido: list[dict] | None,
                        incluir_geom_base: bool = True) -> list[str]:
    mapa = _mapa_campos(campos_pedido)
    partes = ["geom"] if incluir_geom_base else []
    for c in campos_catalogo:
        cfg = mapa.get(c["nome"])
        if cfg and cfg.get("incluir") is False:
            continue
        destino = (cfg or {}).get("destino") or c["nome"]
        partes.append(f'"{c["nome"]}" AS "{destino}"')
    if not partes:
        raise FalhaDefinitiva("nenhum campo selecionado para exportar")
    return partes


def _sql_exportacao(schema: str, tabela: str, campos_catalogo: list[dict], campos_pedido: list[dict] | None,
                    colunas_extra: list[str] | None = None, incluir_geom_base: bool = True) -> str:
    partes = _colunas_exportacao(campos_catalogo, campos_pedido, incluir_geom_base) + list(colunas_extra or [])
    return f'SELECT {", ".join(partes)} FROM "{schema}"."{tabela}"'


def _avisos_de_stderr(stderr: str) -> list[str]:
    avisos = []
    for linha in (stderr or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if any(p in linha for p in (_PISTA_TRUNCAMENTO, _PISTA_CAMPO_RECUSADO, _PISTA_TIPO_MISCONVERSAO)):
            avisos.append(linha)
    return avisos


def _zipar_pasta(pasta: Path, caminho_zip: Path) -> None:
    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for arq in sorted(pasta.rglob("*")):
            if arq.is_file():
                zf.write(arq, arq.relative_to(pasta.parent))


def _estrategia(ctx, formato: str, srid_origem: int, srid_pedido: int | None, geometria: str) -> dict:
    """{driver, destino (Path), dsco, avisos_formato, pos_processar} — `destino` é dentro de `ctx.dir_trabalho`;
    quem chama roda o ogr2ogr e depois `pos_processar(destino) -> (caminho_final, content_type, extensao)`."""
    d = ctx.dir_trabalho
    alvo = srid_pedido or srid_origem
    if formato == "gpkg":
        return {"driver": "GPKG", "destino": d / "saida.gpkg", "t_srs": alvo, "avisos": [],
                "pos": lambda p: (p, "application/geopackage+sqlite3", "gpkg")}
    if formato == "geojson":
        return {"driver": "GeoJSON", "destino": d / "saida.geojson", "t_srs": 4326,
                "avisos": ["GeoJSON só existe em WGS84 (RFC 7946): reprojetado para EPSG:4326"] if alvo != 4326 else [],
                "pos": lambda p: (p, "application/geo+json", "geojson")}
    if formato == "geojsonseq":
        aviso_crs = ["GeoJSONSeq só existe em WGS84 (RFC 7946): reprojetado para EPSG:4326"] if alvo != 4326 else []
        return {"driver": "GeoJSONSeq", "destino": d / "saida.geojsonl", "t_srs": 4326, "avisos": aviso_crs,
                "pos": lambda p: (p, "application/x-ndjson", "geojsonl")}
    if formato == "kml":
        return {"driver": "LIBKML", "destino": d / "saida.kml", "t_srs": 4326,
                "avisos": (["KML só existe em WGS84: reprojetado para EPSG:4326"] if alvo != 4326 else [])
                + ["campo de data vira texto no KML (o driver não tem tipo Date nativo)"],
                "pos": lambda p: (p, "application/vnd.google-earth.kml+xml", "kml")}
    if formato == "csv":
        return {"driver": "CSV", "destino": d / "saida.csv", "t_srs": alvo,
                "lco": ["GEOMETRY=AS_WKT", "STRING_QUOTING=IF_NEEDED"],
                "avisos": ["geometria exportada como texto WKT numa coluna (`WKT`); reimporte com o formato csv "
                          "normal só reconhece latitude/longitude, não WKT"],
                "pos": lambda p: (p, "text/csv", "csv")}
    if formato == "dxf":
        return {"driver": "DXF", "destino": d / "saida.dxf", "t_srs": alvo,
                "avisos": ["DXF não tem atributo arbitrário: só geometria (e Layer/Linetype/EntityHandle/Text) "
                          "sobrevivem — qualquer outro campo é descartado pelo formato, não por nós"],
                "pos": lambda p: (p, "image/vnd.dxf", "dxf")}
    if formato == "shapefile.zip":
        pasta = d / "_shp_saida"
        return {"driver": "ESRI Shapefile", "destino": pasta / "saida.shp", "t_srs": alvo,
                "lco": ["ENCODING=UTF-8"],
                "avisos": ["nome de campo maior que 10 caracteres é truncado pelo Shapefile (DBF); confira os "
                          "avisos de truncamento devolvidos por este job"],
                "pos": lambda p: _zip_e_devolver(pasta, d / "saida.zip", "application/zip", "zip")}
    if formato == "filegdb.zip":
        pasta = d / "_gdb_saida"
        return {"driver": "OpenFileGDB", "destino": pasta / "saida.gdb", "t_srs": alvo, "avisos": [],
                "pos": lambda p: _zip_e_devolver(pasta, d / "saida.zip", "application/zip", "zip")}
    if formato == "xlsx":
        return _estrategia_xlsx(ctx, srid_origem, alvo, geometria)
    if formato == "mvt":
        return _estrategia_mvt(ctx)
    if formato == "pmtiles":
        return {"driver": "PMTiles", "destino": d / "saida.pmtiles", "t_srs": 3857,
                "dsco": [f"MAXZOOM={PMTILES_MAXZOOM_PADRAO}", "MINZOOM=0"],
                "avisos": ["PMTiles usa a grade de tile do mapa-múndi (EPSG:3857) e QUANTIZA a coordenada por "
                          f"tile (padrão do formato); reprojetado de EPSG:{srid_origem} — não é bit-exato, é "
                          "aproximado por natureza do mosaico de tiles (tolerância medida no teste de ida e volta)"],
                "pos": lambda p: (p, "application/vnd.pmtiles", "pmtiles")}
    raise FalhaDefinitiva(f"formato de exportação não suportado nesta instalação: {formato}")


def _zip_e_devolver(pasta: Path, caminho_zip: Path, content_type: str, ext: str):
    _zipar_pasta(pasta, caminho_zip)
    shutil.rmtree(pasta, ignore_errors=True)
    return caminho_zip, content_type, ext


def _estrategia_mvt(ctx) -> dict:
    pasta = ctx.dir_trabalho / "_mvt_saida"
    return {"driver": "MVT", "destino": pasta, "t_srs": 3857,
            "dsco": [f"MAXZOOM={MVT_MAXZOOM_PADRAO}", "MINZOOM=0"],
            "avisos": ["MVT usa a grade de tile do mapa-múndi (EPSG:3857) e QUANTIZA a coordenada por tile "
                      "(padrão do formato); não é bit-exato, é aproximado por natureza do mosaico de tiles "
                      "(tolerância medida no teste de ida e volta) — dataset em diretório, entregue zipado"],
            "pos": lambda p: _zip_e_devolver(pasta, ctx.dir_trabalho / "saida.zip", "application/zip", "zip")}


def _estrategia_xlsx(ctx, srid_origem: int, alvo: int, geometria: str) -> dict:
    """XLSX não tem geometria nativa (medido: `ogrinfo --format XLSX` -> "No support for geometries"). Ponto vira
    `latitude`/`longitude` (o par que `csv_normalizar` já reconhece na reimportação); qualquer outra geometria
    sai só como texto WKT de referência (não reimportável automaticamente — avisado)."""
    d = ctx.dir_trabalho
    e_ponto = (geometria or "").endswith("Point")
    csv_tmp = d / "_xlsx_intermediario.csv"
    if e_ponto:
        colunas_extra = ['ST_Y(ST_Transform(geom, 4674)) AS "latitude"',
                         'ST_X(ST_Transform(geom, 4674)) AS "longitude"']
        avisos = ["geometria exportada como colunas latitude/longitude (EPSG:4674); reimportável pelo caminho "
                  "normal do XLSX (o mesmo do CSV)"]
    else:
        colunas_extra = ['ST_AsText(geom) AS "geom_wkt"']
        avisos = ["XLSX não guarda geometria nativamente (Excel não é um formato espacial): a coluna `geom_wkt` "
                  "é só referência de leitura humana, NÃO é reimportada automaticamente — geometria "
                  f"'{geometria}' precisa de outro formato para ida e volta"]
    return {"driver": "CSV", "destino": csv_tmp, "t_srs": None, "colunas_extra": colunas_extra,
            "incluir_geom_base": False, "avisos": avisos, "pos": lambda p: _csv_para_xlsx(ctx, p)}


def _csv_para_xlsx(ctx, csv_tmp: Path):
    destino = ctx.dir_trabalho / "saida.xlsx"
    r = ctx.subprocesso(["ogr2ogr", "-f", "XLSX", str(destino), str(csv_tmp)])
    if r.returncode != 0:
        raise FalhaDefinitiva(f"não converteu para XLSX: {(r.stderr or '')[-200:]}")
    return destino, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"


def _item_camada(cur, item_id: str) -> dict:
    cur.execute("SELECT id, titulo, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'",
                (item_id,))
    item = cur.fetchone()
    if item is None:
        raise FalhaDefinitiva("camada inexistente (ou não é uma camada_vetorial)")
    return item


@tarefa(
    nome="ingestao.exportar_camada",
    descricao="Exporta uma camada vetorial hospedada para um arquivo, no formato pedido (item L6-02-o)",
    parametros=ExportarCamadaParametros,
    pesado=False,
    memoria_mb=512,
    timeout_s=1800,
    tentativas=1,
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def ingestao_exportar_camada(ctx, item_id: uuid.UUID, formato: str, crs_srid: int | None = None,
                             campos: list[dict] | None = None) -> dict:
    iid = str(item_id)
    with ctx.db() as cur:
        item = _item_camada(cur, iid)
    dados = item["dados"]
    schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
    geometria = dados.get("geometria") or "Geometry"
    campos_catalogo = dados.get("campos") or []

    ctx.progresso(10, "preparando a consulta")
    estrat = _estrategia(ctx, formato, srid, crs_srid, geometria)
    sql = _sql_exportacao(schema, tabela, campos_catalogo, campos, estrat.get("colunas_extra"),
                          estrat.get("incluir_geom_base", True))
    argv = ["ogr2ogr"]
    if estrat.get("driver"):
        argv += ["-f", estrat["driver"]]
    Path(estrat["destino"]).parent.mkdir(parents=True, exist_ok=True)
    argv.append(str(estrat["destino"]))
    argv.append(_pg_conninfo(ctx.tenant_id, ctx.usuario_id))
    for lco in estrat.get("lco", []):
        argv += ["-lco", lco]
    for dsco in estrat.get("dsco", []):
        argv += ["-dsco", dsco]
    if estrat.get("incluir_geom_base", True):
        # achado no L6-02-o: SQL cru (passthrough) para o driver PostgreSQL não carrega a SRS nem o tipo de
        # geometria da coluna "geom" (a fonte é uma consulta, não a tabela catalogada) — sem isso, o arquivo
        # sai SEM CRS gravado (medido: FileGDB com "Layer SRS WKT:" vazio) e o OpenFileGDB chega a recusar
        # "Unsupported geometry type". `-s_srs`/`-t_srs` sempre juntos (mesmo quando iguais: -s_srs sozinho é
        # erro do ogr2ogr) e `-nlt` do tipo já resolvido no catálogo (nunca adivinhado de novo).
        if estrat.get("t_srs"):
            argv += ["-s_srs", f"EPSG:{srid}", "-t_srs", f"EPSG:{estrat['t_srs']}"]
        nlt = geometria.upper() if geometria and geometria != "Geometry" else "GEOMETRY"
        argv += ["-nlt", nlt]
    # sem -dialect: passthrough nativo do Postgres (ST_Transform/ST_Y/ST_AsText não existem no dialeto OGRSQL)
    argv += ["-sql", sql, "--config", "PG_USE_COPY", "YES"]

    ctx.progresso(30, "ogr2ogr")
    r = ctx.subprocesso(argv)
    avisos = list(estrat.get("avisos") or [])
    avisos += _avisos_de_stderr(r.stderr or "")
    if r.returncode != 0:
        linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        raise FalhaDefinitiva(f"ogr2ogr falhou: {(linhas[-1] if linhas else 'sem detalhe')[:200]}")

    ctx.progresso(70, "empacotando")
    caminho_final, content_type, ext = estrat["pos"](estrat["destino"])
    conteudo = Path(caminho_final).read_bytes()
    with ctx.db() as cur:
        obj = objetos.guardar(cur, "exportacao", conteudo, content_type, item_id=ctx.job_id)
        cur.execute("SELECT plat.evento_registrar('camadas/exportar', 'item', %s, %s::jsonb, NULL, NULL)",
                    (iid, json.dumps({"formato": formato, "job_id": str(ctx.job_id)}, default=str)))
    ctx.progresso(100, "concluído")
    return {"item_id": iid, "formato": formato, "chave": obj["chave"], "sha256": obj["sha256"],
            "bytes": obj["bytes"], "content_type": content_type, "extensao": ext, "avisos": avisos}


@tarefa(
    nome="ingestao.exportar_inquilino",
    descricao="Exporta todas as camadas do inquilino num GeoPackage + manifesto JSON (escrow, item L0-06)",
    parametros=ExportarInquilinoParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    perfil_minimo="admin",
    ferramentas=("gdal",),
)
def ingestao_exportar_inquilino(ctx, formato: str = "gpkg+json") -> dict:
    with ctx.db() as cur:
        cur.execute(
            "SELECT id, titulo, dados FROM plat.item WHERE tipo = 'camada_vetorial' AND apagado_em IS NULL "
            "ORDER BY criado_em"
        )
        itens = cur.fetchall()
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        slug = cur.fetchone()["slug"]

    destino_gpkg = ctx.dir_trabalho / "camadas.gpkg"
    manifesto: list[dict] = []
    n = len(itens)
    for i, item in enumerate(itens):
        dados = item["dados"]
        schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
        nome_layer = f"c_{str(item['id']).replace('-', '')[:16]}"
        geometria = dados.get("geometria") or "Geometry"
        nlt = geometria.upper() if geometria != "Geometry" else "GEOMETRY"
        sql = _sql_exportacao(schema, tabela, dados.get("campos") or [], None)
        argv = ["ogr2ogr", "-f", "GPKG", str(destino_gpkg), _pg_conninfo(ctx.tenant_id, ctx.usuario_id),
                "-nln", nome_layer, "-s_srs", f"EPSG:{srid}", "-t_srs", f"EPSG:{srid}", "-nlt", nlt,
                "-sql", sql, "--config", "PG_USE_COPY", "YES"]  # sem -dialect: passthrough nativo do Postgres
        if destino_gpkg.exists():
            argv.append("-update")
        r = ctx.subprocesso(argv)
        if r.returncode != 0:
            linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            raise FalhaDefinitiva(f"exportação do item {item['id']} falhou: "
                                  f"{(linhas[-1] if linhas else 'sem detalhe')[:200]}")
        manifesto.append({
            "item_id": str(item["id"]), "titulo": item["titulo"], "layer_gpkg": nome_layer,
            "schema": schema, "tabela": tabela, "srid": srid, "geometria": dados.get("geometria"),
            "campos": dados.get("campos"), "procedencia": dados.get("procedencia"),
            "estatisticas": dados.get("estatisticas"),
        })
        ctx.progresso(5 + int(85 * (i + 1) / max(1, n)), f"{i + 1} de {n} camadas")

    ctx.progresso(92, "empacotando")
    manifesto_bytes = json.dumps(
        {"inquilino": slug, "gerado_por": "plat ingestao.exportar_inquilino v1", "job_id": str(ctx.job_id),
         "camadas": manifesto}, ensure_ascii=False, default=str, indent=2,
    ).encode("utf-8")
    gpkg_bytes = destino_gpkg.read_bytes() if destino_gpkg.exists() else b""
    with ctx.db() as cur:
        obj_manifesto = objetos.guardar(cur, "exportacao", manifesto_bytes, "application/json", item_id=ctx.job_id)
        obj_gpkg = (objetos.guardar(cur, "exportacao", gpkg_bytes, "application/geopackage+sqlite3",
                                    item_id=ctx.job_id) if gpkg_bytes else None)
        cur.execute("SELECT plat.evento_registrar('org/exportar', 'tenant', %s, %s::jsonb, NULL, NULL)",
                    (str(ctx.tenant_id), json.dumps({"camadas": n, "job_id": str(ctx.job_id)}, default=str)))
    ctx.progresso(100, "concluído")
    return {"camadas": n, "manifesto_chave": obj_manifesto["chave"], "manifesto_sha256": obj_manifesto["sha256"],
            "gpkg_chave": (obj_gpkg or {}).get("chave"), "gpkg_bytes": (obj_gpkg or {}).get("bytes", 0)}
