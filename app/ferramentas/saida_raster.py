"""Publicação do resultado RASTER de uma ferramenta (item L2-05-e).

O caminho é o mesmo da ingestão de imagem (item L1-01), só que a origem é a análise e não um envio: o
produto já sai COG validado do diretório de trabalho, sobe ao armazenamento de objetos endereçado por
conteúdo, nasce como item STAC na coleção `<tenant_id>-analises` do inquilino e como `plat.item` do tipo
`raster`, com miniatura, estatísticas por banda, o bloco de proveniência e uma relação `derivado_de` para
cada entrada. Nada aqui reimplementa o que o L1-01 já escreveu — a coleção, o espelho `plat.raster_item`
e o formato do asset são os mesmos, e é o que faz o resultado aparecer no mesmo mapa e no mesmo motor de
ladrilho das imagens ingeridas.

A saída da ferramenta é `{"familia": "raster", "arquivo": Path (COG pronto), "metodo": str,
"bandas": [{"nome": ...}], "cog": {...}, "resumo": {...}}`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pyproj
import rasterio

from app import limites, objetos
from app.catalogo import miniatura as miniatura_catalogo
from app.catalogo import tipos as tipos_item
from app.catalogo.comum import jsonb
from app.imagens import pgstac as ps
from app.imagens import raster_item as ri
from app.imagens.cog import versoes_software
from app.raster import comandos

SLUG_COLECAO = "analises"
EXTENSOES_STAC = (
    "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
    "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
    "https://stac-extensions.github.io/file/v2.1.0/schema.json",
)


def colecao_garantir(cur, tenant_id: int) -> str:
    colecao_id = ps.nome_colecao(tenant_id, SLUG_COLECAO)
    if ps.colecao_obter(cur, tenant_id, colecao_id) is None:
        ps.colecao_criar(cur, tenant_id, SLUG_COLECAO, {
            "title": "Resultados de análise",
            "description": "Coleção STAC dos rasters produzidos pelas ferramentas de análise "
                           "(item L2-05-e); cada item traz a proveniência da execução.",
        })
    return colecao_id


def estatisticas(caminho, amostra: int = limites.RASTER_ESTATISTICA_AMOSTRA) -> list[dict]:
    """min/max/média/desvio por banda, por amostragem regular — nunca lê o raster inteiro."""
    saida = []
    with rasterio.open(caminho) as ds:
        passo = max(1, int(((ds.width * ds.height) / max(amostra, 1)) ** 0.5))
        for i in range(1, ds.count + 1):
            arr = ds.read(i)[::passo, ::passo].astype("float64")
            nd = ds.nodatavals[i - 1]
            if nd is not None:
                arr = arr[arr != nd]
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                saida.append({"banda": i, "min": None, "max": None, "mean": None, "std": None, "nodata": nd})
                continue
            saida.append({"banda": i, "min": float(arr.min()), "max": float(arr.max()),
                          "mean": float(arr.mean()), "std": float(arr.std()), "nodata": nd})
    return saida


def _geometria_4326(ds) -> tuple[dict, list[float]]:
    b = ds.bounds
    cantos = [(b.left, b.bottom), (b.right, b.bottom), (b.right, b.top), (b.left, b.top)]
    if ds.crs and ds.crs.to_epsg() != 4326:
        tf = pyproj.Transformer.from_crs(ds.crs, "EPSG:4326", always_xy=True)
        cantos = [tf.transform(x, y) for x, y in cantos]
    anel = [[round(x, 7), round(y, 7)] for x, y in cantos]
    anel.append(anel[0])
    lons = [p[0] for p in anel]
    lats = [p[1] for p in anel]
    return {"type": "Polygon", "coordinates": [anel]}, [min(lons), min(lats), max(lons), max(lats)]


def miniatura(ctx, cog_caminho, env: dict):
    """PNG pequeno do produto (8 bits, escalado): o COG de análise costuma ser float ou classe, e o driver
    PNG não escreve float — por isso o `-ot Byte -scale`, e não a miniatura do L1-01 (que parte de um COG
    visual já em 8 bits)."""
    destino = ctx.dir_trabalho / "miniatura.png"
    with rasterio.open(cog_caminho) as ds:
        lado = max(ds.width, ds.height)
        bandas = min(ds.count, 3)
    fator = min(1.0, limites.RASTER_VISUAL_MAX_LADO / lado)
    argv = ["gdal_translate", "-of", "PNG", "-ot", "Byte", "-scale"]
    for b in range(1, bandas + 1):
        argv += ["-b", str(b)]
    if fator < 1.0:
        argv += ["-outsize", f"{max(1, int(fator * 100))}%", f"{max(1, int(fator * 100))}%"]
    argv += [str(cog_caminho), str(destino)]
    comandos.rodar(ctx, argv, env, "miniatura do resultado")
    return destino


def publicar(ctx, f, saida: dict, destino: dict, entradas: dict, prov: dict, titulo: str | None,
             custo: int, request=None) -> dict:
    """Sobe o COG, cria o item STAC e o item de catálogo. Devolve o mesmo formato do resultado vetorial,
    com `feicoes` = número de pixels válidos declarado pela ferramenta (ou None)."""
    item_id = destino["item_id"]
    caminho = saida["arquivo"]
    env = saida.get("env") or {}
    with rasterio.open(caminho) as ds:
        epsg = ds.crs.to_epsg() if ds.crs else None
        contagem_bandas = ds.count
        nodata = list(ds.nodatavals)
        forma = [ds.height, ds.width]
        transform = list(ds.transform)[:6]
        geometria, bbox = _geometria_4326(ds)
    stats = estatisticas(caminho)
    png = miniatura_catalogo.normalizar(miniatura(ctx, caminho, env).read_bytes())

    ctx.progresso(85, "subindo o resultado ao armazenamento")
    with ctx.db() as cur:
        objeto = objetos.guardar_arquivo(cur, "raster", caminho, "image/tiff", item_id=item_id,
                                         usuario_id=ctx.usuario_id)
    with ctx.db() as cur:
        obj_mini = objetos.guardar(cur, "raster", png, "image/png", item_id=item_id, usuario_id=ctx.usuario_id)

    titulo_final = (titulo or f"{f.titulo}: " + ", ".join(e["titulo"] for e in entradas.values()))[:250] or f.titulo
    quando = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    bandas = saida.get("bandas") or [{"nome": f"banda_{i}"} for i in range(1, contagem_bandas + 1)]
    stac = {
        "type": "Feature", "stac_version": "1.0.0", "stac_extensions": list(EXTENSOES_STAC),
        "id": item_id, "collection": ps.nome_colecao(ctx.tenant_id, SLUG_COLECAO),
        "geometry": geometria, "bbox": [round(v, 7) for v in bbox],
        "properties": {
            "datetime": quando, "title": titulo_final, "proj:epsg": epsg, "proj:shape": forma,
            "proj:transform": transform, "plat:perfil": "cientifico", "plat:nodata": nodata,
            "plat:ferramenta": prov, "plat:metodo": saida.get("metodo"),
            "plat:resumo": saida.get("resumo"), "plat:cog": saida.get("cog"),
            "plat:versoes": versoes_software(),
        },
        "assets": {
            "cientifico": {
                "href": f"/api/objetos/{objeto['chave']}", "type": tipo_cog,
                "title": "COG do resultado da análise", "roles": ["data"],
                "file:checksum": f"1220{objeto['sha256']}", "file:size": objeto["bytes"],
                "raster:bands": [{"nodata": s.get("nodata"), "statistics": {
                    "minimum": s["min"], "maximum": s["max"], "mean": s["mean"], "stddev": s["std"]}}
                    if s.get("min") is not None else {"nodata": s.get("nodata")} for s in stats],
            },
            "miniatura": {"href": f"/api/objetos/{obj_mini['chave']}", "type": "image/png",
                          "title": "miniatura do resultado", "roles": ["thumbnail"],
                          "file:checksum": f"1220{obj_mini['sha256']}", "file:size": obj_mini["bytes"]},
        },
        "links": [],
    }
    dados_item = {
        "colecao": stac["collection"], "stac_id": item_id, "perfil": "cientifico", "origem": "copiado",
        "srid_nativo": epsg or 0, "bandas": bandas,
        "procedencia": {"gerador": f"plat ferramenta {f.nome} v{f.versao}", "metodo": saida.get("metodo"),
                        "sha256": objeto["sha256"], "job_id": prov["job_id"], "ferramenta": prov},
    }
    tipos_item.validar("raster", dados_item)

    ctx.progresso(92, "publicando no catálogo")
    bytes_totais = objeto["bytes"] + obj_mini["bytes"]
    with ctx.db() as cur:
        colecao_id = colecao_garantir(cur, ctx.tenant_id)
        ps.item_criar(cur, ctx.tenant_id, colecao_id, stac)
        ri.espelhar(cur, ctx.tenant_id, colecao_id, item_id,
                    {"sha256": objeto["sha256"], "perfil": "cientifico", "bytes": objeto["bytes"],
                     "estado": "ativo"})
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, extent, "
            "extent_origem, criado_por, modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, "
            "ST_MakeEnvelope(%s,%s,%s,%s,4326), 'dado', %s, %s)",
            [item_id, ctx.tenant_id, titulo_final, ctx.usuario_id, jsonb(dados_item), bytes_totais,
             *[round(v, 7) for v in bbox], ctx.usuario_id, ctx.usuario_id],
        )
        miniatura_catalogo.guardar(cur, item_id, png)
        for e in entradas.values():
            cur.execute("INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id) VALUES (%s::uuid, "
                        "%s::uuid, 'derivado_de', %s) ON CONFLICT DO NOTHING",
                        (item_id, e["item_id"], ctx.tenant_id))
        cur.execute("UPDATE plat.tenant SET uso_bytes = uso_bytes + %s WHERE id = %s",
                    (bytes_totais, ctx.tenant_id))
        props = {"ferramenta": f.nome, "versao": f.versao, "job_id": prov["job_id"],
                 "entradas": [e["item_id"] for e in entradas.values()], "familia": "raster"}
        if request is not None:
            from app.auth.comum import registrar_evento

            registrar_evento(cur, request, "analises/executar", "item", item_id, props)
        else:
            cur.execute("SELECT plat.evento_registrar('analises/executar', 'item', %s, %s::jsonb, NULL, NULL)",
                        (item_id, json.dumps(props, default=str)))
        try:
            cur.execute("SELECT pgstac.update_collection_extents()")
        except Exception as e:  # extents são derivados: nunca derrubam a publicação
            ctx.log("AVISO", f"update_collection_extents falhou: {e}")
    ctx.entrada(item_id, objeto["sha256"], "COG do resultado")
    ctx.progresso(100, "concluído")
    return {"item_id": item_id, "titulo": titulo_final, "feicoes": saida.get("pixels_validos"),
            "sha256": objeto["sha256"], "familia": "raster", "bytes": objeto["bytes"],
            "cog": saida.get("cog"), "resumo": saida.get("resumo"), "custo": custo, "entradas": ctx.entradas}


__all__ = ["SLUG_COLECAO", "colecao_garantir", "estatisticas", "miniatura", "publicar"]
