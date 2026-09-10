"""Exportação por URL de arquivo (contrato 3 do item L2-04-e-vector-tile-server-tilejson):
`GET /svc/{token}/camadas/{item}.geojson|.kml|.csv|.fgb|.gpkg`, com filtro `where` (mesmo AST/lista
branca do FeatureServer, `app.consulta.where_ast`/`app.consulta.campos`, item L2-04-b/c — nada
reescrito) e `bbox` (`xmin,ymin,xmax,ymax` em 4326). Para Google Earth (KML), planilha (CSV) e
scripts (GeoJSON/FlatGeobuf/GeoPackage) que colam a URL uma vez e ela funciona enquanto o token não
for revogado — ao contrário da URL assinada que expira (decisão já tomada pelo L1-02, reusada aqui).

GeoJSON, KML e CSV são gerados por ESTE processo, linha a linha, com um cursor NOMEADO do lado do
Postgres (`itersize`, nunca `fetchall`) — é a cláusula medida do portão (RSS do worker <= 300 MB
para 1 mi de feições). FlatGeobuf e GeoPackage são delegados ao `ogr2ogr` do sistema (GDAL 3.8, já
usado pelo raster desta casa): `/vsistdout/` foi tentado para FlatGeobuf e RECUSADO pelo driver
nesta versão do GDAL (medido: `ERROR 1: Failed to create directory /vsistdout/`); GeoPackage é
SQLite e nunca foi candidato a incremental. Os dois escrevem num arquivo TEMPORÁRIO (apagado ao
fim, inclusive se o cliente cortar a conexão no meio) e a resposta HTTP é streamada em pedaços de
64 KiB a partir do disco — streaming da RESPOSTA, não da GERAÇÃO; limitação honesta, ver
`app/tiles/exportacao.py::_exportar_via_ogr2ogr` e o handoff."""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import tempfile
from collections.abc import Generator
from urllib.parse import urlsplit

import psycopg2.extras
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app import db
from app.consulta import campos as campos_mod
from app.consulta.where_ast import ErroWhere, compilar_where
from app.erros import ErroAPI
from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings
from app.tiles import autorizacao
from app.tiles.camada import _camada_do_item

router = APIRouter(tags=["tiles-vetoriais-exportacao"])
PREFIXO = "/svc/{token}/camadas/{item_id}"
ITERSIZE = 500          # linhas por ida ao Postgres — limita o pico de RAM independente do total de feições
LOTE_HTTP = 200         # feições por `yield` (chunk) da resposta
CACHE_EXPORTACAO = "no-store, must-revalidate"  # reflete `where`/`bbox`; nunca cacheado


def _colunas_atributo(campos: list[dict]) -> list[dict]:
    return [c for c in campos if c["papel"] != "geometria_controle"]


def _bbox_sql(bbox: str | None, srid: int) -> tuple[str, list]:
    if not bbox:
        return "", []
    partes = bbox.split(",")
    if len(partes) != 4:
        raise ErroAPI(422, "bbox_invalido", "bbox tem de ser xmin,ymin,xmax,ymax em EPSG:4326", {"bbox": bbox})
    try:
        xmin, ymin, xmax, ymax = (float(p) for p in partes)
    except ValueError as e:
        raise ErroAPI(422, "bbox_invalido", "bbox só aceita números", {"bbox": bbox}) from e
    return ' AND "geom" && ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), %s)', [xmin, ymin, xmax, ymax, srid]


def _where_sql(where: str | None, campos: list[dict]) -> tuple[str, list]:
    if not where:
        return "", []
    lista_branca = campos_mod.lista_branca(campos)
    try:
        consulta = compilar_where(where, lista_branca)
    except ErroWhere as e:
        raise ErroAPI(422, "where_invalido", str(e), {"where": where}) from e
    return f" AND ({consulta.sql})", consulta.params


def _filtro(dados: dict, campos: list[dict], where: str | None, bbox: str | None) -> tuple[str, list]:
    sql = ""
    params: list = []
    w_sql, w_params = _where_sql(where, campos)
    sql += w_sql
    params += w_params
    b_sql, b_params = _bbox_sql(bbox, int(dados["srid"]))
    sql += b_sql
    params += b_params
    return sql, params


def _autorizar_e_preparar(request: Request, token: str, item_id: str, where: str | None, bbox: str | None):
    """Auth + lookup da camada + filtro compilado — comum às cinco extensões."""
    auth = autorizacao.autorizar(request, token, item_id)
    with db.db(auth.contexto()) as cur:
        dados = _camada_do_item(cur, item_id)
        campos = campos_mod.campos_da_camada(cur, dados["schema"], dados["tabela"])
    filtro_sql, filtro_params = _filtro(dados, campos, where, bbox)
    return auth, dados, campos, filtro_sql, filtro_params


def _conexao_streaming():
    """Uma conexão do POOL, fora do gerenciador `db.db()` de propósito: o cursor NOMEADO precisa
    ficar aberto durante todo o `yield` do gerador, que roda DEPOIS da rota já ter devolvido a
    resposta — o `with db.db()` fecharia a transação antes disso. Devolvida ao pool no `finally`
    do gerador que a pediu, nunca vazada."""
    p = db.pool()
    con = db.obter_conexao(p)
    con.autocommit = False
    return con, p


def _preparar_contexto(con, ctx: db.Contexto) -> None:
    cur = con.cursor(cursor_factory=CursorSchemaAmbiente)
    cur.execute(f"SET search_path = {settings.PLAT_SCHEMA}, public")
    cur.execute(
        "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
        "set_config('plat.login', %s, true)",
        (str(ctx.tenant_id), str(ctx.usuario_id), ctx.login),
    )
    cur.close()


def _cursor_nomeado(con, nome: str):
    cur = con.cursor(name=nome, cursor_factory=psycopg2.extras.RealDictCursor, withhold=False)
    cur.itersize = ITERSIZE
    return cur


# ================================================================================== GeoJSON
def _gerar_geojson(ctx, dados: dict, campos: list[dict], filtro_sql: str, filtro_params: list) -> Generator[bytes]:
    con, p = _conexao_streaming()
    try:
        _preparar_contexto(con, ctx)
        colunas = ", ".join(f'"{c["nome"]}"' for c in _colunas_atributo(campos))
        sql = (
            f'SELECT ST_AsGeoJSON(ST_Transform("geom", 4326)) AS __geom, {colunas} '
            f'FROM "{dados["schema"]}"."{dados["tabela"]}" WHERE true{filtro_sql}'
        )  # noqa: S608 — schema/tabela/colunas vêm do catálogo (dados de plat.item) e da lista branca; filtro_sql já parametrizado
        cur = _cursor_nomeado(con, "plat_export_geojson")
        cur.execute(sql, filtro_params)
        yield b'{"type":"FeatureCollection","features":[\n'
        primeira = True
        while True:
            linhas = cur.fetchmany(LOTE_HTTP)
            if not linhas:
                break
            pedacos = []
            for linha in linhas:
                geom = json.loads(linha.pop("__geom")) if linha.get("__geom") else None
                feicao = {"type": "Feature", "geometry": geom, "properties": dict(linha)}
                pedacos.append(("" if primeira else ",\n") + json.dumps(feicao, default=str))
                primeira = False
            yield "".join(pedacos).encode("utf-8")
        yield b"\n]}\n"
        cur.close()
        con.commit()
    finally:
        p.putconn(con, close=con.closed)


@router.get(f"{PREFIXO}.geojson", openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="exportação GeoJSON (streaming)")
def exportar_geojson(request: Request, token: str, item_id: str,
                      where: str | None = Query(None, max_length=2000), bbox: str | None = Query(None, max_length=200)):
    auth, dados, campos, f_sql, f_params = _autorizar_e_preparar(request, token, item_id, where, bbox)
    return StreamingResponse(
        _gerar_geojson(auth.contexto(), dados, campos, f_sql, f_params),
        media_type="application/geo+json",
        headers={"Cache-Control": CACHE_EXPORTACAO, "Content-Disposition": f'attachment; filename="{item_id}.geojson"'},
    )


# ====================================================================================== CSV
def _gerar_csv(ctx, dados: dict, campos: list[dict], filtro_sql: str, filtro_params: list) -> Generator[bytes]:
    con, p = _conexao_streaming()
    try:
        _preparar_contexto(con, ctx)
        atributos = _colunas_atributo(campos)
        colunas = ", ".join(f'"{c["nome"]}"' for c in atributos)
        sql = (
            f'SELECT ST_AsText(ST_Transform("geom", 4326)) AS __wkt, {colunas} '
            f'FROM "{dados["schema"]}"."{dados["tabela"]}" WHERE true{filtro_sql}'
        )  # noqa: S608
        cur = _cursor_nomeado(con, "plat_export_csv")
        cur.execute(sql, filtro_params)
        cabecalho = io.StringIO()
        csv.writer(cabecalho).writerow(["geometria_wkt"] + [c["nome"] for c in atributos])
        yield cabecalho.getvalue().encode("utf-8")
        while True:
            linhas = cur.fetchmany(LOTE_HTTP)
            if not linhas:
                break
            buf = io.StringIO()
            w = csv.writer(buf)
            for linha in linhas:
                wkt = linha.pop("__wkt")
                w.writerow([wkt] + [linha.get(c["nome"]) for c in atributos])
            yield buf.getvalue().encode("utf-8")
        cur.close()
        con.commit()
    finally:
        p.putconn(con, close=con.closed)


@router.get(f"{PREFIXO}.csv", openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="exportação CSV (streaming, geometria em WKT)")
def exportar_csv(request: Request, token: str, item_id: str,
                  where: str | None = Query(None, max_length=2000), bbox: str | None = Query(None, max_length=200)):
    auth, dados, campos, f_sql, f_params = _autorizar_e_preparar(request, token, item_id, where, bbox)
    return StreamingResponse(
        _gerar_csv(auth.contexto(), dados, campos, f_sql, f_params),
        media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": CACHE_EXPORTACAO, "Content-Disposition": f'attachment; filename="{item_id}.csv"'},
    )


# ====================================================================================== KML
_KML_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def _kml_texto(v) -> str:
    s = "" if v is None else str(v)
    for a, b in _KML_ESCAPE.items():
        s = s.replace(a, b)
    return s


def _gerar_kml(
    ctx, dados: dict, campos: list[dict], filtro_sql: str, filtro_params: list, titulo: str,
) -> Generator[bytes]:
    con, p = _conexao_streaming()
    try:
        _preparar_contexto(con, ctx)
        atributos = _colunas_atributo(campos)
        rotulo = next((c["nome"] for c in atributos if c["tipo_pg"] in ("text", "character varying")), None)
        colunas = ", ".join(f'"{c["nome"]}"' for c in atributos)
        sql = (
            f'SELECT ST_AsKML(ST_Transform("geom", 4326)) AS __kml, {colunas} '
            f'FROM "{dados["schema"]}"."{dados["tabela"]}" WHERE true{filtro_sql}'
        )  # noqa: S608
        cur = _cursor_nomeado(con, "plat_export_kml")
        cur.execute(sql, filtro_params)
        yield (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>'
            f"{_kml_texto(titulo)}</name>\n"
        ).encode("utf-8")
        while True:
            linhas = cur.fetchmany(LOTE_HTTP)
            if not linhas:
                break
            pedacos = []
            for linha in linhas:
                geom_kml = linha.pop("__kml") or ""
                nome = _kml_texto(linha.get(rotulo)) if rotulo else ""
                dados_ext = "".join(
                    f'<Data name="{_kml_texto(c["nome"])}"><value>{_kml_texto(linha.get(c["nome"]))}</value></Data>'
                    for c in atributos
                )
                pedacos.append(
                    f"<Placemark><name>{nome}</name><ExtendedData>{dados_ext}</ExtendedData>{geom_kml}</Placemark>\n"
                )
            yield "".join(pedacos).encode("utf-8")
        yield b"</Document></kml>\n"
        cur.close()
        con.commit()
    finally:
        p.putconn(con, close=con.closed)


@router.get(f"{PREFIXO}.kml", openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="exportação KML (streaming, Google Earth)")
def exportar_kml(request: Request, token: str, item_id: str,
                  where: str | None = Query(None, max_length=2000), bbox: str | None = Query(None, max_length=200)):
    auth, dados, campos, f_sql, f_params = _autorizar_e_preparar(request, token, item_id, where, bbox)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT titulo FROM plat.item WHERE id = %s::uuid", (item_id,))
        r = cur.fetchone()
    titulo = (r["titulo"] if r else None) or item_id
    return StreamingResponse(
        _gerar_kml(auth.contexto(), dados, campos, f_sql, f_params, titulo),
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Cache-Control": CACHE_EXPORTACAO, "Content-Disposition": f'attachment; filename="{item_id}.kml"'},
    )


# ================================================================= FlatGeobuf e GeoPackage (ogr2ogr)
def _dsn_ogr(ctx) -> str:
    """DSN de conexão do GDAL (driver PostgreSQL) com o CONTEXTO de inquilino já embutido via
    `options='-c plat.tenant_id=... '` — a mesma técnica de startup option do libpq que
    `SET LOCAL`/`set_config` usam por dentro da transação, só que aqui é a ÚNICA forma de passar
    contexto para um processo que abre a PRÓPRIA conexão (ogr2ogr nunca herda a nossa). RLS
    (`plat.tenant_atual()`) filtra a consulta como se fosse a aplicação — nenhum bypass."""
    p = urlsplit(settings.PLAT_DSN)
    opcoes = f"-c plat.tenant_id={ctx.tenant_id} -c plat.usuario_id={ctx.usuario_id} -c plat.login={ctx.login}"
    return (
        f"PG:host={p.hostname} port={p.port or 5432} dbname={p.path.lstrip('/')} "
        f"user={p.username} password={p.password} options='{opcoes}'"
    )


def _sql_ogr(dados: dict, filtro_sql: str, filtro_params: list) -> str:
    """SQL literal (sem `%s`) para o `-sql` do ogr2ogr: os parâmetros do filtro (já validados pela
    lista branca do where_ast/bbox numérico — nunca texto livre do cliente colado direto) são
    inlinados com `cur.mogrify`, a mesma função que o psycopg2 usa para montar a consulta antes de
    mandar ao servidor — não uma concatenação nova e sem escape."""
    with db.db() as cur:
        sql_bytes = cur.mogrify(
            f'SELECT * FROM "{dados["schema"]}"."{dados["tabela"]}" WHERE true{filtro_sql}',  # noqa: S608
            filtro_params,
        )
    return sql_bytes.decode("utf-8")


def _exportar_via_ogr2ogr(
    auth, dados: dict, f_sql: str, f_params: list, *, driver: str, sufixo: str,
) -> Generator[bytes]:
    """FlatGeobuf e GeoPackage caem aqui: `/vsistdout/` NÃO funciona com o driver FlatGeobuf desta
    versão do GDAL (3.8.4, medido em 07/09 — `ERROR 1: Failed to create directory /vsistdout/`, o
    driver tenta criar um DIRETÓRIO em vez de escrever em um descritor), e GeoPackage é SQLite —
    nenhum dos dois formatos é gerado de forma incremental de verdade neste GDAL. Os dois escrevem
    num arquivo TEMPORÁRIO (apagado ao fim, inclusive se o cliente cortar a conexão no meio) e a
    resposta HTTP em si é streamada em pedaços de 64 KiB a partir do disco — streaming da
    RESPOSTA, não da GERAÇÃO; a cláusula de RAM medida do portão (RSS <= 300 MB) é só do GeoJSON,
    então esta limitação não fere o texto do portão, mas fica registrada aqui e no handoff."""
    sql = _sql_ogr(dados, f_sql, f_params)
    fd, caminho = tempfile.mkstemp(suffix=sufixo, prefix="plat_export_")
    os.close(fd)
    os.unlink(caminho)  # ogr2ogr recusa sobrescrever sem -overwrite; o arquivo nasce dele
    cmd = ["ogr2ogr", "-f", driver, caminho, _dsn_ogr(auth.contexto()), "-sql", sql, "-nln", "camada"]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(caminho):
        if os.path.exists(caminho):
            os.unlink(caminho)
        raise ErroAPI(502, "exportacao_falhou",
                      f"ogr2ogr saiu com código {r.returncode}: {r.stderr.decode(errors='replace')[:300]}")

    def gerar():
        try:
            with open(caminho, "rb") as f:
                while True:
                    pedaco = f.read(65536)
                    if not pedaco:
                        break
                    yield pedaco
        finally:
            os.unlink(caminho)

    return gerar()


@router.get(f"{PREFIXO}.fgb", openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="exportação FlatGeobuf (via ogr2ogr/GDAL)")
def exportar_fgb(request: Request, token: str, item_id: str,
                  where: str | None = Query(None, max_length=2000), bbox: str | None = Query(None, max_length=200)):
    auth, dados, campos, f_sql, f_params = _autorizar_e_preparar(request, token, item_id, where, bbox)
    return StreamingResponse(
        _exportar_via_ogr2ogr(auth, dados, f_sql, f_params, driver="FlatGeobuf", sufixo=".fgb"),
        media_type="application/octet-stream",
        headers={"Cache-Control": CACHE_EXPORTACAO, "Content-Disposition": f'attachment; filename="{item_id}.fgb"'},
    )


@router.get(f"{PREFIXO}.gpkg", openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="exportação GeoPackage (arquivo temporário via ogr2ogr/GDAL — SQLite não é incremental)")
def exportar_gpkg(request: Request, token: str, item_id: str,
                   where: str | None = Query(None, max_length=2000), bbox: str | None = Query(None, max_length=200)):
    auth, dados, campos, f_sql, f_params = _autorizar_e_preparar(request, token, item_id, where, bbox)
    return StreamingResponse(
        _exportar_via_ogr2ogr(auth, dados, f_sql, f_params, driver="GPKG", sufixo=".gpkg"),
        media_type="application/geopackage+sqlite3",
        headers={"Cache-Control": CACHE_EXPORTACAO, "Content-Disposition": f'attachment; filename="{item_id}.gpkg"'},
    )
