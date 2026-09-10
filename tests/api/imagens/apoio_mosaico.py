"""Semeadura de N COGs ADJACENTES (grade contígua, sem sobreposição, sem lacuna) para os testes do
item L1-07 (mosaico por busca STAC registrada). Cada quadrante tem um valor de banda CONSTANTE e
DISTINTO (`100 + 40*indice`, sempre < 65535): é o que permite provar pela JUNTA de dois quadrantes
que o ladrilho do mosaico tem pixel dos DOIS lados — uma medição, não uma inspeção visual. Mesmo
canto geográfico de `apoio_raster.py` (Brasília, dado sintético; nenhum dado de cliente na suíte).

Datas e nuvem DISTINTAS por quadrante (a ordem "mais recente primeiro" fica testável: o quadrante 0
é o mais recente) e uma sobreposição TEMPORAL proposital nos dois últimos índices sobre a MESMA célula
geográfica (mesmo lugar, épocas diferentes) — usada pelo teste de seleção "primeira com dado vence"."""

from __future__ import annotations

import datetime
import subprocess
import tempfile
import uuid
from pathlib import Path

LADO_PX = 200
RESOLUCAO = 20.0  # m/px -> 4 km por quadrante: pequeno de propósito (máquina com pouco disco/RAM)
CANTO_LON, CANTO_LAT = -47.95, -15.75


def semear_grade(tenant_id: int, slug: str, n_col: int = 3, n_lin: int = 2,
                 colecao_slug: str = "mosaicoteste") -> dict:
    """Grade `n_col × n_lin` de COGs contíguos (padrão 3×2 = 6, o mínimo do portão) numa coleção
    dedicada `<tenant>-<colecao_slug>`. Devolve `{colecao, itens: [...], grade}`; cada item tem
    `item_id`, `indice`, `col`, `lin`, `valor` (o DN constante, para conferência de pixel), `datetime`,
    `nuvem`, `bbox`."""
    from app import db, objetos
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="teste")
    with db.db(ctx) as cur:
        objetos.garantir_bucket(cur, tenant_id, slug)

    import pyproj
    import rasterio
    tf = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lado_m = LADO_PX * RESOLUCAO
    colecao = ps.nome_colecao(tenant_id, colecao_slug)
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    itens = []
    hoje = datetime.datetime(2026, 8, 18, 13, 30, tzinfo=datetime.timezone.utc)

    with db.db(ctx) as cur:
        if ps.colecao_obter(cur, tenant_id, colecao) is None:
            ps.colecao_criar(cur, tenant_id, colecao_slug, {
                "title": "Grade de teste do mosaico (L1-07)",
                "description": "Quadrantes sintéticos ADJACENTES para provar mosaico e pegadas; "
                "apagados ao fim da suíte/da prova viva — não é dado de produto."})

    indice = 0
    for lin in range(n_lin):
        for col in range(n_col):
            valor = 100 + 40 * indice
            item_id = str(uuid.uuid4())
            with tempfile.TemporaryDirectory() as tmp:
                cog = Path(tmp) / f"q{indice}.tif"
                # gera já na posição certa da grade: origem deslocada por (col, lin) quadrantes
                import numpy as np
                from rasterio.transform import from_origin
                x0, y0 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(
                    CANTO_LON, CANTO_LAT)
                x0 += col * lado_m
                y0 -= lin * lado_m
                banda = np.full((LADO_PX, LADO_PX), valor, dtype="uint16")
                bruto = Path(tmp) / f"bruto{indice}.tif"
                with rasterio.open(bruto, "w", driver="GTiff", height=LADO_PX, width=LADO_PX, count=4,
                                   dtype="uint16", crs="EPSG:3857", nodata=0,
                                   transform=from_origin(x0, y0, RESOLUCAO, RESOLUCAO)) as dst:
                    for i in range(1, 5):
                        dst.write(banda, i)
                subprocess.run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=ZSTD",
                                "-co", "BLOCKSIZE=128", str(bruto), str(cog)], check=True)
                with db.db(ctx) as cur:
                    objeto = objetos.guardar_arquivo(cur, "raster", cog, "image/tiff", item_id=item_id,
                                                     usuario_id=usuario_id)
                with rasterio.open(cog) as ds:
                    oeste, sul, leste, norte = ds.bounds
                lon0, lat0 = tf.transform(oeste, sul)
                lon1, lat1 = tf.transform(leste, norte)
                bbox = [min(lon0, lon1), min(lat0, lat1), max(lon0, lon1), max(lat0, lat1)]
                geometry = {"type": "Polygon", "coordinates": [[
                    [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]],
                ]]}
                quando = hoje - datetime.timedelta(days=indice)  # índice 0 = mais recente
                nuvem = round(indice * 3.5, 1)
                asset = {"href": f"/api/objetos/{objeto['chave']}", "type": tipo_cog}
                stac = {
                    "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
                    "geometry": geometry, "bbox": bbox,
                    "properties": {
                        "datetime": quando.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "title": f"quadrante de teste do mosaico {indice} (col {col}, lin {lin})",
                        "eo:cloud_cover": nuvem,
                        "plat:valor_teste": valor,
                    },
                    "assets": {"cientifico": {**asset, "roles": ["data"]}, "visual": {**asset, "roles": ["visual"]}},
                    "links": [],
                }
                with db.db(ctx) as cur:
                    ps.item_criar(cur, tenant_id, colecao, stac)
                    ri.espelhar(cur, tenant_id, colecao, item_id, {
                        "sha256": objeto["sha256"], "perfil": "cientifico", "bytes": objeto["bytes"],
                        "estado": "ativo"})
                    cur.execute(
                        "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                        "criado_por, modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
                        (item_id, tenant_id, stac["properties"]["title"], usuario_id,
                         jsonb({"colecao": colecao, "stac_id": item_id, "perfil": "cientifico",
                                "origem": "copiado", "srid_nativo": 3857}),
                         objeto["bytes"], usuario_id, usuario_id))
            itens.append({"item_id": item_id, "indice": indice, "col": col, "lin": lin, "valor": valor,
                         "datetime": stac["properties"]["datetime"], "nuvem": nuvem, "bbox": bbox})
            indice += 1

    return {
        "tenant_id": tenant_id, "colecao": colecao,
        "itens": itens, "grade": {"n_col": n_col, "n_lin": n_lin, "lado_m": lado_m, "lado_px": LADO_PX,
                                  "resolucao": RESOLUCAO},
    }


def semear_sobrepostas(tenant_id: int, slug: str, valores: list[int],
                       colecao_slug: str = "mosaicosobreposto") -> dict:
    """N COGs no MESMO lugar (footprint idêntico, sem deslocamento de grade), um valor CONSTANTE
    distinto por item — para o item L1-08 (mínimo): compor por `mediana`/`media`/`maxima`/`minima`
    sobre cenas que REALMENTE se sobrepõem tem resposta numérica exata e previsível (mediana de
    [10,20,90] é 20; média é 40), ao contrário da grade adjacente de `semear_grade` (feita para provar
    a JUNTA, não a sobreposição). Mesma disciplina de dado sintético (Brasília, nenhum dado de cliente).
    `valores[0]` é o mais RECENTE (datetime decrescente pelo índice, mesma convenção de `semear_grade`)."""
    import numpy as np
    import pyproj
    import rasterio
    from rasterio.transform import from_origin

    from app import db, objetos
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="teste")
    with db.db(ctx) as cur:
        objetos.garantir_bucket(cur, tenant_id, slug)

    tf = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    colecao = ps.nome_colecao(tenant_id, colecao_slug)
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    hoje = datetime.datetime(2026, 8, 18, 13, 30, tzinfo=datetime.timezone.utc)
    itens = []

    with db.db(ctx) as cur:
        if ps.colecao_obter(cur, tenant_id, colecao) is None:
            ps.colecao_criar(cur, tenant_id, colecao_slug, {
                "title": "Cenas sobrepostas de teste do mosaico (L1-08)",
                "description": "COGs sintéticos no MESMO lugar, valores distintos, para provar as "
                "regras de composição por pixel — apagados ao fim da suíte, não é dado de produto."})

    x0, y0 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(
        CANTO_LON, CANTO_LAT)
    for indice, valor in enumerate(valores):
        item_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as tmp:
            cog = Path(tmp) / f"s{indice}.tif"
            banda = np.full((LADO_PX, LADO_PX), valor, dtype="uint16")
            bruto = Path(tmp) / f"bruto{indice}.tif"
            with rasterio.open(bruto, "w", driver="GTiff", height=LADO_PX, width=LADO_PX, count=4,
                               dtype="uint16", crs="EPSG:3857", nodata=0,
                               transform=from_origin(x0, y0, RESOLUCAO, RESOLUCAO)) as dst:
                for i in range(1, 5):
                    dst.write(banda, i)
            subprocess.run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=ZSTD",
                            "-co", "BLOCKSIZE=128", str(bruto), str(cog)], check=True)
            with db.db(ctx) as cur:
                objeto = objetos.guardar_arquivo(cur, "raster", cog, "image/tiff", item_id=item_id,
                                                 usuario_id=usuario_id)
            with rasterio.open(cog) as ds:
                oeste, sul, leste, norte = ds.bounds
            lon0, lat0 = tf.transform(oeste, sul)
            lon1, lat1 = tf.transform(leste, norte)
            bbox = [min(lon0, lon1), min(lat0, lat1), max(lon0, lon1), max(lat0, lat1)]
            geometry = {"type": "Polygon", "coordinates": [[
                [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]],
            ]]}
            quando = hoje - datetime.timedelta(days=indice)  # índice 0 = mais recente
            asset = {"href": f"/api/objetos/{objeto['chave']}", "type": tipo_cog}
            stac = {
                "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
                "geometry": geometry, "bbox": bbox,
                "properties": {
                    "datetime": quando.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "title": f"cena sobreposta de teste do mosaico {indice} (valor {valor})",
                    "eo:cloud_cover": float((len(valores) - indice) * 3),
                    "plat:valor_teste": valor,
                },
                "assets": {"cientifico": {**asset, "roles": ["data"]}, "visual": {**asset, "roles": ["visual"]}},
                "links": [],
            }
            with db.db(ctx) as cur:
                ps.item_criar(cur, tenant_id, colecao, stac)
                ri.espelhar(cur, tenant_id, colecao, item_id, {
                    "sha256": objeto["sha256"], "perfil": "cientifico", "bytes": objeto["bytes"],
                    "estado": "ativo"})
                cur.execute(
                    "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                    "criado_por, modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
                    (item_id, tenant_id, stac["properties"]["title"], usuario_id,
                     jsonb({"colecao": colecao, "stac_id": item_id, "perfil": "cientifico",
                            "origem": "copiado", "srid_nativo": 3857}),
                     objeto["bytes"], usuario_id, usuario_id))
        itens.append({"item_id": item_id, "indice": indice, "valor": valor,
                     "datetime": stac["properties"]["datetime"], "bbox": bbox})

    return {"tenant_id": tenant_id, "colecao": colecao, "itens": itens}


def apagar_grade(tenant_id: int, grade: dict) -> None:
    """Limpeza determinística (teste e prova viva): apaga item STAC + espelho + catálogo + objeto de
    cada quadrante. Não apaga a COLEÇÃO nem o BUCKET do inquilino: `plat_app` não é dona das tabelas
    de partição do pgstac (o gatilho `collection_delete_trigger_func` roda `DROP TABLE` como dono do
    schema pgstac) — apagar a coleção vazia é operação de administração do pgstac, fora do escopo
    desta suíte; uma coleção de teste vazia é inofensiva (mesmo padrão já visto em `pgstac.collections`
    de outras suítes desta casa)."""
    from app import db, objetos

    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")
    colecao = grade["colecao"]
    for it in grade["itens"]:
        item_id = it["item_id"]
        with db.db(ctx) as cur:
            cur.execute("SELECT chave FROM plat.arquivo WHERE tenant_id = %s AND referencia = %s",
                        (tenant_id, item_id))
            chaves = [r["chave"] for r in cur.fetchall()]
            cur.execute("DELETE FROM plat.raster_item WHERE tenant_id = %s AND item_id = %s", (tenant_id, item_id))
            cur.execute("DELETE FROM plat.item WHERE tenant_id = %s AND id = %s::uuid", (tenant_id, item_id))
            cur.execute("SET LOCAL search_path = pgstac, public")
            cur.execute("SELECT pgstac.delete_item(%s, %s)", (item_id, colecao))
        for chave in chaves:
            try:
                objetos.apagar(chave)
            except Exception:
                pass


__all__ = ["apagar_grade", "semear_grade", "semear_sobrepostas"]
