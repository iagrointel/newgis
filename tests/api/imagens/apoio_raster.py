"""Semeadura de um raster de VERDADE para os testes do serviço de ladrilho (item L1-02).

Gera um COG de 4 bandas (16 bits, EPSG:3857, ~1024x1024 sobre Brasília), sobe ao balde do inquilino
pelo mesmo caminho da ingestão (`objetos.guardar_arquivo`, nome por conteúdo) e cria o item STAC no
pgstac + a linha em `plat.raster_item`. É deliberadamente sintético: nenhum dado de cliente entra na
suíte, e o padrão de vegetação alternada dá NDVI com contraste visível.

Idempotente por conteúdo: o objeto tem o nome do sha256, então rodar de novo não duplica bytes; o item
STAC ganha um id novo a cada chamada (é barato e evita colisão entre execuções da suíte)."""

from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

LARGURA = 1024
RESOLUCAO = 20.0
CANTO_LON, CANTO_LAT = -47.95, -15.75


def _gerar_cog(destino: Path) -> Path:
    import numpy as np
    import pyproj
    import rasterio
    from rasterio.transform import from_origin

    tf = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = tf.transform(CANTO_LON, CANTO_LAT)
    yy, xx = np.mgrid[0:LARGURA, 0:LARGURA]
    veg = ((np.sin(xx / 60.0) + np.cos(yy / 45.0)) > 0).astype("float32")
    bandas = [
        (400 + 300 * (1 - veg) + (xx % 17)).astype("uint16"),   # azul
        (700 + 200 * veg + (yy % 13)).astype("uint16"),         # verde
        (900 + 1200 * (1 - veg)).astype("uint16"),              # vermelho
        (1200 + 2600 * veg).astype("uint16"),                   # infravermelho próximo
    ]
    bruto = destino.with_name("bruto.tif")
    with rasterio.open(bruto, "w", driver="GTiff", height=LARGURA, width=LARGURA, count=4,
                       dtype="uint16", crs="EPSG:3857", nodata=0,
                       transform=from_origin(x0, y0, RESOLUCAO, RESOLUCAO)) as dst:
        for i, b in enumerate(bandas, start=1):
            dst.write(b, i)
    subprocess.run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=ZSTD", "-co", "BLOCKSIZE=512",
                    str(bruto), str(destino)], check=True)
    bruto.unlink(missing_ok=True)
    return destino


def semear_raster(tenant_id: int, slug: str) -> dict:
    from app import db, objetos
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    # `plat.usuario` tem RLS: sem contexto de inquilino a consulta volta vazia (achado ao escrever este
    # apoio). O contexto mínimo (usuário 0) basta para ler; depois o contexto é refeito com o dono real.
    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="teste")
    item_id = str(uuid.uuid4())
    with tempfile.TemporaryDirectory() as tmp:
        cog = _gerar_cog(Path(tmp) / "teste4b.tif")
        with db.db(ctx) as cur:
            objetos.garantir_bucket(cur, tenant_id, slug)
        with db.db(ctx) as cur:
            objeto = objetos.guardar_arquivo(cur, "raster", cog, "image/tiff", item_id=item_id,
                                             usuario_id=usuario_id)
    colecao = ps.nome_colecao(tenant_id, "imagens")
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    asset = {"href": f"/api/objetos/{objeto['chave']}", "type": tipo_cog}
    stac = {
        "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
        "geometry": {"type": "Polygon", "coordinates": [[
            [CANTO_LON, CANTO_LAT], [CANTO_LON + 0.19, CANTO_LAT], [CANTO_LON + 0.19, CANTO_LAT - 0.19],
            [CANTO_LON, CANTO_LAT - 0.19], [CANTO_LON, CANTO_LAT]]]},
        "bbox": [CANTO_LON, CANTO_LAT - 0.19, CANTO_LON + 0.19, CANTO_LAT],
        "properties": {"datetime": "2026-01-01T00:00:00Z", "title": "COG sintético de teste (4 bandas)"},
        "assets": {"cientifico": {**asset, "roles": ["data"]}, "visual": {**asset, "roles": ["visual"]}},
        "links": [],
    }
    with db.db(ctx) as cur:
        if ps.colecao_obter(cur, tenant_id, colecao) is None:
            ps.colecao_criar(cur, tenant_id, "imagens", {
                "title": "Imagens do inquilino",
                "description": "Coleção STAC das imagens ingeridas pela plataforma."})
        ps.item_criar(cur, tenant_id, colecao, stac)
        ri.espelhar(cur, tenant_id, colecao, item_id, {
            "sha256": objeto["sha256"], "perfil": "cientifico", "bytes": objeto["bytes"], "estado": "ativo"})
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (item_id, tenant_id, "COG sintético de teste", usuario_id,
             jsonb({"colecao": colecao, "stac_id": item_id, "perfil": "cientifico", "origem": "copiado",
                    "srid_nativo": 3857, "bandas": [{"nome": f"banda_{i}"} for i in range(1, 5)]}),
             objeto["bytes"], usuario_id, usuario_id))
    return {"item_id": item_id, "colecao": colecao, "chave": objeto["chave"], "tenant_id": tenant_id}
