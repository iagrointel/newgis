#!/usr/bin/env python3
"""Bancada do item L1-07: mosaico de >= 6 cenas Sentinel-2 ABERTAS (recortes pequenos).

O portão do item pede, verbatim: "mosaico de >= 6 cenas Sentinel-2 abertas (recortes pequenos)
registrado pela tela; tile do mosaico em z 8-14 medido (frio/quente) em `tests/medidas/L1-07.json`".
A medição que existia usava uma grade SINTÉTICA 3x2 gerada em memória — prova o compositor, não prova
que o produto abre cena real, com a geometria, o tipo e a escala de uma cena de satélite de verdade.

Aqui as cenas são reais: catálogo público Element84 (`earth-search.aws.element84.com`, sem chave),
bucket público `sentinel-cogs` da AWS, e de cada cena se lê apenas uma JANELA pequena por `/vsicurl`
(nunca a cena inteira: são ~1 GB cada). O recorte vira um COG local, entra no armazenamento do
inquilino e no catálogo STAC pelo mesmo caminho de qualquer imagem do produto.

Uso:
  scripts/bench_l107_sentinel.py --tenant-slug demo --saida tests/medidas/L1-07.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

BUSCA = "https://earth-search.aws.element84.com/v1/search"
BANDAS = ("red", "green", "blue")
LADO_PX = 512          # recorte pequeno: 512x512 a 10 m/px = 5,12 km de lado
COLECAO_SLUG = "l107sentinel"


def buscar_cenas(bbox, desde, ate, minimo, nuvem_max=20.0) -> list[dict]:
    corpo = json.dumps({
        "collections": ["sentinel-2-l2a"], "bbox": bbox,
        "datetime": f"{desde}/{ate}", "query": {"eo:cloud_cover": {"lt": nuvem_max}},
        "limit": 50,
    }).encode()
    req = urllib.request.Request(BUSCA, data=corpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        dados = json.load(r)
    feicoes = dados.get("features", [])
    # uma cena por DATA, para que o mosaico componha datas diferentes e não duplicatas do mesmo dia
    por_data: dict[str, dict] = {}
    for f in feicoes:
        dia = f["properties"]["datetime"][:10]
        if dia not in por_data and all(b in f["assets"] for b in BANDAS):
            por_data[dia] = f
    cenas = list(por_data.values())
    if len(cenas) < minimo:
        raise SystemExit(f"o catálogo devolveu {len(cenas)} datas distintas; o portão pede {minimo}")
    return cenas[:minimo]


def recortar(cena: dict, centro_lon: float, centro_lat: float, destino: Path) -> dict:
    """Lê uma janela de LADO_PX px ao redor do centro, nas 3 bandas visíveis, direto do COG remoto."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import Window

    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
    caminhos = [f"/vsicurl/{cena['assets'][b]['href']}" for b in BANDAS]
    with rasterio.open(caminhos[0]) as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [centro_lon], [centro_lat])
        linha, coluna = src.index(xs[0], ys[0])
        janela = Window(coluna - LADO_PX // 2, linha - LADO_PX // 2, LADO_PX, LADO_PX)
        perfil = src.profile
        transformada = src.window_transform(janela)
        crs = src.crs
    pilha = []
    for caminho in caminhos:
        with rasterio.open(caminho) as src:
            pilha.append(src.read(1, window=janela))
    arranjo = np.stack(pilha)
    bruto = destino.with_name("bruto_" + destino.name)
    perfil.update(driver="GTiff", height=LADO_PX, width=LADO_PX, count=len(BANDAS),
                  dtype=arranjo.dtype, transform=transformada, crs=crs, nodata=0)
    for chave in ("blockxsize", "blockysize", "tiled", "compress", "interleave", "predictor"):
        perfil.pop(chave, None)
    with rasterio.open(bruto, "w", **perfil) as dst:
        dst.write(arranjo)
    subprocess.run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=DEFLATE",
                    "-co", "BLOCKSIZE=256", str(bruto), str(destino)], check=True)
    bruto.unlink(missing_ok=True)
    with rasterio.open(destino) as ds:
        limites = ds.bounds
        epsg = ds.crs.to_epsg()
    return {"bounds_nativo": list(limites), "epsg": epsg, "bytes": destino.stat().st_size}


def semear(tenant_id: int, tenant_slug: str, cenas: list[dict],
           centro_lon: float, centro_lat: float) -> dict:
    """Põe cada recorte no armazenamento do inquilino e no catálogo STAC, como qualquer imagem."""
    import pyproj
    import rasterio

    from app import db, objetos
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    with db.db(db.Contexto(tenant_id=tenant_id, usuario_id=0, login="bench")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id,))
        usuario_id = cur.fetchone()["id"]
    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="bench")
    with db.db(ctx) as cur:
        objetos.garantir_bucket(cur, tenant_id, tenant_slug)
    colecao = ps.nome_colecao(tenant_id, COLECAO_SLUG)
    with db.db(ctx) as cur:
        if ps.colecao_obter(cur, tenant_id, colecao) is None:
            ps.colecao_criar(cur, tenant_id, COLECAO_SLUG, {
                "title": "Recortes Sentinel-2 L2A abertos (bancada do item L1-07)",
                "description": "Janelas pequenas de cenas reais do catálogo público Element84, "
                               "lidas por /vsicurl do bucket sentinel-cogs."})
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    itens = []
    with tempfile.TemporaryDirectory() as tmp:
        for cena in cenas:
            item_id = str(uuid.uuid4())
            destino = Path(tmp) / f"{cena['id']}.tif"
            t0 = time.perf_counter()
            info = recortar(cena, centro_lon, centro_lat, destino)
            ms_recorte = (time.perf_counter() - t0) * 1000
            with db.db(ctx) as cur:
                objeto = objetos.guardar_arquivo(cur, "raster", destino, "image/tiff",
                                                 item_id=item_id, usuario_id=usuario_id)
            para4326 = pyproj.Transformer.from_crs(f"EPSG:{info['epsg']}", "EPSG:4326", always_xy=True)
            with rasterio.open(destino) as ds:
                o, s, l, n = ds.bounds
            cantos = [para4326.transform(px, py) for px, py in ((o, s), (l, s), (l, n), (o, n))]
            lons = [p[0] for p in cantos]
            lats = [p[1] for p in cantos]
            bbox = [min(lons), min(lats), max(lons), max(lats)]
            asset = {"href": f"/api/objetos/{objeto['chave']}", "type": tipo_cog}
            stac = {
                "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
                "geometry": {"type": "Polygon",
                             "coordinates": [[list(p) for p in cantos] + [list(cantos[0])]]},
                "bbox": bbox,
                "properties": {
                    "datetime": cena["properties"]["datetime"],
                    "title": f"recorte de {cena['id']}",
                    "eo:cloud_cover": cena["properties"].get("eo:cloud_cover"),
                    "proj:epsg": info["epsg"],
                    "plat:cena_origem": cena["id"],
                    "plat:fonte": "Sentinel-2 L2A (Copernicus/ESA) via earth-search.aws.element84.com",
                },
                "assets": {"cientifico": {**asset, "roles": ["data"]},
                           "visual": {**asset, "roles": ["visual"]}},
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
                            "origem": "copiado", "srid_nativo": info["epsg"]}),
                     objeto["bytes"], usuario_id, usuario_id))
            itens.append({"item_id": item_id, "cena": cena["id"],
                          "datetime": cena["properties"]["datetime"],
                          "nuvem": cena["properties"].get("eo:cloud_cover"),
                          "epsg": info["epsg"], "bytes": info["bytes"], "ms_recorte": round(ms_recorte, 1),
                          "bbox": bbox})
    return {"tenant_id": tenant_id, "colecao": colecao, "itens": itens}


def medir(dados: dict, zooms: tuple[int, ...], cliente, tok: str) -> dict:
    """Ladrilho do mosaico em z 8-14, frio e quente, pelo MESMO caminho da rota.

    Mede o MOTOR, não o nginx: o cache de borda é o item L1-02-d. `frio` é a primeira leitura daquele
    ladrilho; `quente` é a mediana de 5 repetições da mesma URL. O mosaico é registrado pela rota de
    criação, a mesma que a tela usa."""
    from app.imagens import tiles

    itens = dados["itens"]
    lons = [(i["bbox"][0] + i["bbox"][2]) / 2 for i in itens]
    lats = [(i["bbox"][1] + i["bbox"][3]) / 2 for i in itens]
    centro_lon, centro_lat = sum(lons) / len(lons), sum(lats) / len(lats)

    r = cliente.post(f"/svc/{tok}/stac/mosaicos",
                     json={"nome": "bancada L1-07 Sentinel-2", "collections": [dados["colecao"]]})
    if r.status_code != 201:
        raise RuntimeError(f"não foi possível registrar o mosaico: {r.status_code} {r.text[:300]}")
    mosaico_id = r.json()["id"]
    medidas = {}
    try:
        for z in zooms:
            t = tiles.TMS.tile(centro_lon, centro_lat, z)
            caminho = f"/svc/{tok}/mosaico/{mosaico_id}/{z}/{t.x}/{t.y}.png"
            inicio = time.perf_counter()
            primeira = cliente.get(caminho)
            ms_frio = (time.perf_counter() - inicio) * 1000
            repeticoes = []
            ultima = primeira
            for _ in range(5):
                i2 = time.perf_counter()
                ultima = cliente.get(caminho)
                repeticoes.append((time.perf_counter() - i2) * 1000)
            medidas[f"z{z}"] = {
                "status_frio": primeira.status_code,
                "bytes": len(primeira.content),
                "ms_frio": round(ms_frio, 1),
                "ms_quente_mediana": round(statistics.median(repeticoes), 1),
                "status_quente": ultima.status_code,
            }
    finally:
        cliente.delete(f"/svc/{tok}/stac/mosaicos/{mosaico_id}")
    return {"mosaico_id": mosaico_id, "centro": [centro_lon, centro_lat], "por_zoom": medidas}


def montar_saida(dados: dict, resultado: dict, tenant_slug: str, lon: float, lat: float) -> dict:
    sha = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    comando = (f"bash /home/dev/plataforma/laco/roda_teste.sh tests/api/imagens/test_l107_sentinel_real.py "
               f"-W ignore -q   (PLAT_GRAVAR_MEDIDAS=1 para regravar)  "
               f"[{len(dados['itens'])} cenas Sentinel-2 L2A ABERTAS do catalogo publico Element84, "
               f"recortes de {LADO_PX}x{LADO_PX} px a 10 m/px lidos por /vsicurl do bucket sentinel-cogs; "
               f"mosaico registrado pela rota de criacao; ladrilho medido pelo motor]")
    saida = {
        "item": "L1-07-mosaico-por-colecao-e-pegadas",
        "gerado_em": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": sha,
        "fonte_das_cenas": {
            "catalogo": "https://earth-search.aws.element84.com/v1 (Element84, publico, sem chave)",
            "colecao": "sentinel-2-l2a",
            "armazenamento": "s3://sentinel-cogs (publico), lido por /vsicurl",
            "licenca": "Copernicus Sentinel data — uso aberto",
            "recorte": f"{LADO_PX}x{LADO_PX} px a 10 m/px (~5,1 km de lado), bandas red/green/blue",
            "por_que_recorte": "a cena inteira tem ~1 GB; o portao pede 'recortes pequenos'",
            "centro": [lon, lat],
        },
        "cenas": [{"cena": i["cena"], "datetime": i["datetime"], "nuvem": i["nuvem"],
                   "epsg": i["epsg"], "bytes": i["bytes"], "ms_recorte": i["ms_recorte"]}
                  for i in dados["itens"]],
        "medidas": {},
    }
    saida["medidas"]["cenas_sentinel2_abertas_no_mosaico"] = {
        "valor": len(dados["itens"]), "unidade": "cenas Sentinel-2 abertas", "comando": comando}
    for z, m in resultado["por_zoom"].items():
        saida["medidas"][f"ladrilho_{z}_frio_ms"] = {
            "valor": m["ms_frio"], "unidade": "ms", "comando": comando}
        saida["medidas"][f"ladrilho_{z}_quente_mediana_ms"] = {
            "valor": m["ms_quente_mediana"], "unidade": "ms", "comando": comando}
        saida["medidas"][f"ladrilho_{z}_bytes"] = {
            "valor": m["bytes"], "unidade": "bytes", "comando": comando}
    saida["detalhe"] = resultado
    return saida


# ⛔ Este arquivo NAO tem entrada de linha de comando. Criar token de serviço exige SESSÃO
# (app/auth/rotas_tokens.py, `so_sessao=True`), e montar uma sessão fora da suíte significaria ler o
# arquivo de credenciais por fora — exatamente o que a casa evita. A bancada roda como teste, em
# tests/api/imagens/test_l107_sentinel_real.py, que já tem a sessão pelas fixtures.
