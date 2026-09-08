"""Semeadura de rasters e de camadas de polígonos para os testes das ferramentas raster (item L2-05-e).

Os rasters são gerados aqui, pequenos e determinísticos, e entram no inquilino pelo MESMO caminho da
ingestão: objeto no armazenamento (nome por conteúdo), item STAC no pgstac, linha em `plat.raster_item`
e item `raster` no catálogo. Nada de dado de cliente entra na suíte.

Quatro superfícies, cada uma pelo que ela prova:
* `dem_projetado`  — elevação em EPSG:32723 (métrico): declividade, visibilidade, curvas de nível;
* `dem_geografico` — a MESMA superfície em EPSG:4326: é o que a ferramenta tem de recusar para
  declividade sem escala declarada (a refutação do adversário);
* `classes`        — uso do solo em quatro classes, uint8 com nodata: zonais e vetorização;
* `duas_bandas`    — vermelho e infravermelho sintéticos, uint16: calculadora.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

LADO = 768   # maior que o bloco do COG (512): é o que faz a pirâmide existir e poder ser conferida
RESOLUCAO = 30.0
X0, Y0 = 300_000.0, 7_400_000.0      # UTM 23S, sobre o litoral paulista
LON0, LAT0 = -47.90, -15.70          # o mesmo relevo, em graus
GRAU = 0.00027777777778


def _superficie() -> np.ndarray:
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    return (200.0 + 60.0 * np.sin(xx / 25.0) + 40.0 * np.cos(yy / 18.0)
            + 0.35 * xx + 0.15 * yy).astype("float32")


def gerar_dem(destino: Path, *, geografico: bool = False) -> Path:
    arr = _superficie()
    if geografico:
        transform = from_origin(LON0, LAT0, GRAU, GRAU)
        crs = "EPSG:4326"
    else:
        transform = from_origin(X0, Y0, RESOLUCAO, RESOLUCAO)
        crs = "EPSG:32723"
    return _escrever_cog(destino, [arr], crs, transform, "float32", nodata=-9999.0)


def gerar_classes(destino: Path) -> Path:
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    arr = (((xx // 32) + (yy // 48)) % 4 + 1).astype("uint8")
    arr[0:20, 0:20] = 0                      # nodata declarado
    return _escrever_cog(destino, [arr], "EPSG:32723", from_origin(X0, Y0, RESOLUCAO, RESOLUCAO),
                         "uint8", nodata=0)


def gerar_duas_bandas(destino: Path, *, nodata=None) -> Path:
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    veg = ((np.sin(xx / 20.0) + np.cos(yy / 15.0)) > 0).astype("float32")
    vermelho = (900 + 1200 * (1 - veg) + (xx % 11)).astype("uint16")
    infra = (1200 + 2600 * veg + (yy % 7)).astype("uint16")
    return _escrever_cog(destino, [vermelho, infra], "EPSG:32723",
                         from_origin(X0, Y0, RESOLUCAO, RESOLUCAO), "uint16", nodata=nodata)


def _escrever_cog(destino: Path, bandas: list, crs: str, transform, dtype: str, nodata) -> Path:
    bruto = destino.with_name("bruto_" + destino.name)
    with rasterio.open(bruto, "w", driver="GTiff", height=bandas[0].shape[0], width=bandas[0].shape[1],
                       count=len(bandas), dtype=dtype, crs=crs, nodata=nodata, transform=transform) as ds:
        for i, b in enumerate(bandas, start=1):
            ds.write(b, i)
    subprocess.run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=ZSTD", "-co", "BLOCKSIZE=256",
                    str(bruto), str(destino)], check=True)
    bruto.unlink(missing_ok=True)
    return destino


def semear(tenant_id: int, slug: str, caminho: Path, titulo: str) -> dict:
    """Publica o arquivo como item `raster` do inquilino (objeto + STAC + espelho + item)."""
    from app import db, objetos
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="teste")
    item_id = str(uuid.uuid4())
    with db.db(ctx) as cur:
        objetos.garantir_bucket(cur, tenant_id, slug)
    with db.db(ctx) as cur:
        objeto = objetos.guardar_arquivo(cur, "raster", caminho, "image/tiff", item_id=item_id,
                                         usuario_id=usuario_id)
    with rasterio.open(caminho) as ds:
        epsg = ds.crs.to_epsg()
        bandas = ds.count
        b = ds.bounds
        if epsg != 4326:
            import pyproj

            tf = pyproj.Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
            cantos = [tf.transform(x, y) for x, y in
                      [(b.left, b.bottom), (b.right, b.bottom), (b.right, b.top), (b.left, b.top)]]
        else:
            cantos = [(b.left, b.bottom), (b.right, b.bottom), (b.right, b.top), (b.left, b.top)]
    anel = [[round(x, 7), round(y, 7)] for x, y in cantos]
    anel.append(anel[0])
    lons = [p[0] for p in anel]
    lats = [p[1] for p in anel]
    colecao = ps.nome_colecao(tenant_id, "imagens")
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    asset = {"href": f"/api/objetos/{objeto['chave']}", "type": tipo_cog,
             "file:checksum": f"1220{objeto['sha256']}", "file:size": objeto["bytes"]}
    stac = {
        "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
        "geometry": {"type": "Polygon", "coordinates": [anel]},
        "bbox": [min(lons), min(lats), max(lons), max(lats)],
        "properties": {"datetime": "2026-01-01T00:00:00Z", "title": titulo, "proj:epsg": epsg},
        "assets": {"cientifico": {**asset, "roles": ["data"]}, "visual": {**asset, "roles": ["visual"]}},
        "links": [],
    }
    with db.db(ctx) as cur:
        if ps.colecao_obter(cur, tenant_id, colecao) is None:
            ps.colecao_criar(cur, tenant_id, "imagens", {
                "title": "Imagens do inquilino", "description": "Coleção STAC das imagens do inquilino."})
        ps.item_criar(cur, tenant_id, colecao, stac)
        ri.espelhar(cur, tenant_id, colecao, item_id, {
            "sha256": objeto["sha256"], "perfil": "cientifico", "bytes": objeto["bytes"], "estado": "ativo"})
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (item_id, tenant_id, titulo, usuario_id,
             jsonb({"colecao": colecao, "stac_id": item_id, "perfil": "cientifico", "origem": "copiado",
                    "srid_nativo": epsg, "bandas": [{"nome": f"banda_{i}"} for i in range(1, bandas + 1)]}),
             objeto["bytes"], usuario_id, usuario_id))
    return {"id": item_id, "item_id": item_id, "colecao": colecao, "chave": objeto["chave"],
            "titulo": titulo, "epsg": epsg, "caminho_local": str(caminho)}


# ---------------------------------------------------------------- camada de polígonos
def criar_camada_poligonos(env, sessao, slug: str, poligonos: list[tuple[str, list]], srid: int = 32723,
                           geometria: str = "Polygon") -> dict:
    """Cria d_<slug>.c_<16 hex> com nome/anel e o item de catálogo. `poligonos` = [(nome, anel)] com o anel
    em coordenadas do `srid`."""
    import json

    from tests import jobs_sessao
    from tests.api.conftest import PREFIXO_TESTE
    from tests.api.test_rls import contexto, ids_por_slug

    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
            adm = cur.fetchone()["usuario_id"]
        contexto(con, ids[slug], usuario_id=adm, login="admin")
        item_id = str(uuid.uuid4())
        tabela = "c_" + uuid.UUID(item_id).hex[:16]
        schema = f"d_{slug}"
        with con.cursor() as cur:
            cur.execute("SELECT to_regnamespace(%s) IS NULL AS falta", (schema,))
            if cur.fetchone()["falta"]:
                cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            cur.execute(f'CREATE TABLE "{schema}"."{tabela}" (fid bigserial PRIMARY KEY, nome text, '
                        f'geom geometry({geometria}, {srid}))')
            for nome, anel in poligonos:
                gj = json.dumps({"type": "Polygon", "coordinates": [anel]})
                cur.execute(f'INSERT INTO "{schema}"."{tabela}"(nome, geom) VALUES (%s, '
                            f'ST_SetSRID(ST_GeomFromGeoJSON(%s), {srid}))', (nome, gj))
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)", (schema, tabela, srid, geometria, adm))
        con.commit()
    finally:
        con.close()
    r = sessao.post("/api/itens", json={
        "id": item_id, "tipo": "camada_vetorial", "titulo": f"{PREFIXO_TESTE} zonas {tabela[-6:]}",
        "dados": {"schema": schema, "tabela": tabela, "geometria": geometria, "srid": srid,
                  "campos": [{"nome": "nome", "tipo": "text"}], "fonte": "hospedada"},
    })
    assert r.status_code == 201, r.text
    return {"id": r.json()["id"], "schema": schema, "tabela": tabela, "feicoes": len(poligonos),
            "titulo": r.json()["titulo"]}


def quadrado(col: float, lin: float, largura_px: float, altura_px: float, *, res: float = RESOLUCAO,
             x0: float = X0, y0: float = Y0) -> list:
    """Anel de um quadrado dado em pixels da grade dos rasters de teste."""
    xa, xb = x0 + col * res, x0 + (col + largura_px) * res
    ya, yb = y0 - (lin + altura_px) * res, y0 - lin * res
    return [[xa, ya], [xb, ya], [xb, yb], [xa, yb], [xa, ya]]
