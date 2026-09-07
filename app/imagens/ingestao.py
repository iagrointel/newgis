"""Job `imagens.ingestar` (item L1-01-ingest-raster; ADR 20260906T2127): a vertical inteira da hipótese —
objeto `arquivo` já enviado (upload retomável, L0-04-a) vira COG validado pelo rio-cogeo nos dois perfis
(visual + científico, `app/imagens/cog.py`), sobe ao Garage por `objetos.guardar_arquivo` (stream, nome por
sha256), nasce como item STAC no pgstac (coleção `<tenant_id>-imagens`, criada sob demanda) e como
`plat.item` tipo `raster` (o uuid do item É o stac_id — ADR decisão 1), com miniatura 600×400 e
estatísticas. Tempo e taxa de compressão por job ficam no `resultado` (portão: "tempo e taxa de compressão
registrados por job").

Ordem das gravações (pensada para cancelamento/retentativa):
1. tudo o que é caro (download, validação, conversão) acontece ANTES de qualquer linha nova no catálogo;
2. os objetos sobem um por transação curta (regra do ContextoJob: trabalho longo fora do `with ctx.db()`);
   são endereçados por conteúdo, então uma retentativa não duplica nem corrompe;
3. a escrita no catálogo (coleção STAC, item STAC, raster_item, plat.item, miniatura) é UMA transação só —
   ou o item inteiro aparece, ou nada aparece; objetos órfãos de uma falha no meio são varríveis por
   `objetos.varrer_orfaos`.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime

import pyproj
from pydantic import BaseModel, Field

from app import limites, objetos
from app.catalogo import tipos as tipos_item
from app.catalogo.comum import jsonb
from app.catalogo import miniatura as miniatura_catalogo
from app.imagens import cog, pgstac as ps, raster_item as ri
from app.imagens.cog import ErroConversao
from app.imagens.validacao import RecusaValidacao, validar
from app.jobs.registro import FalhaDefinitiva, tarefa

EXTENSOES_STAC = (
    "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
    "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
    "https://stac-extensions.github.io/file/v2.1.0/schema.json",
)
SLUG_COLECAO = "imagens"


class IngestarParametros(BaseModel):
    arquivo_id: uuid.UUID
    titulo: str | None = Field(default=None, max_length=250)
    epsg_declarado: int | None = Field(default=None, ge=1, le=999999)


def _colecao_garantir(cur, tenant_id: int) -> str:
    colecao_id = ps.nome_colecao(tenant_id, SLUG_COLECAO)
    if ps.colecao_obter(cur, tenant_id, colecao_id) is None:
        ps.colecao_criar(cur, tenant_id, SLUG_COLECAO, {
            "title": "Imagens do inquilino",
            "description": "Coleção STAC das imagens ingeridas pela plataforma (upload -> COG -> pgstac; "
            "item L1-01-ingest-raster).",
        })
    return colecao_id


def _geometria_4326(rel) -> tuple[dict, list[float]]:
    """BBox do raster reprojetado para EPSG:4326 (cantos transformados um a um — cobre rotação e faixas
    UTM; o anel fecha no primeiro ponto)."""
    gt = rel.geotransform
    x0, px, rx, y0, ry, py = gt
    largura, altura = rel.largura, rel.altura
    cantos = [
        (x0, y0),
        (x0 + largura * px, y0 + largura * rx),
        (x0 + largura * px + altura * ry, y0 + largura * rx + altura * py),
        (x0 + altura * ry, y0 + altura * py),
    ]
    tf = pyproj.Transformer.from_crs(f"EPSG:{rel.epsg}", "EPSG:4326", always_xy=True)
    pontos = [tf.transform(x, y) for x, y in cantos]
    lons = [p[0] for p in pontos]
    lats = [p[1] for p in pontos]
    anel = [[round(lon, 7), round(lat, 7)] for lon, lat in pontos]
    anel.append(anel[0])
    bbox = [min(lons), min(lats), max(lons), max(lats)]
    return {"type": "Polygon", "coordinates": [anel]}, [round(v, 7) for v in bbox]


def _asset_objeto(o: dict, papel: list[str], titulo: str, tipo_midia: str) -> dict:
    return {
        "href": f"/api/objetos/{o['chave']}",
        "type": tipo_midia,
        "title": titulo,
        "roles": papel,
        "file:checksum": f"1220{o['sha256']}",
        "file:size": o["bytes"],
    }


def _item_stac(
    item_id: str, colecao_id: str, titulo: str, rel, stats: list[dict], geometria: dict, bbox: list[float],
    objetos_ref: dict, versoes: dict, nodata_final: list,
) -> dict:
    quando = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    raster_bandas = []
    for st in stats:
        if st.get("min") is None:
            raster_bandas.append({"nodata": st.get("nodata")})
        else:
            raster_bandas.append({
                "nodata": st.get("nodata"),
                "statistics": {
                    "minimum": st["min"], "maximum": st["max"], "mean": st["mean"], "stddev": st["std"],
                    "valid_percent": 100.0,
                },
            })
    tipo_cog = "image/tiff; application=geotiff; profile=cloud-optimized"
    assets = {
        "visual": {
            **_asset_objeto(objetos_ref["visual"], ["visual"], "COG visual (8 bits, JPEG/WEBP)", tipo_cog),
            "plat:compressao": objetos_ref["visual"]["compressao"],
        },
        "cientifico": {
            **_asset_objeto(objetos_ref["cientifico"], ["data"], "COG científico (dtype original, ZSTD)", tipo_cog),
            "raster:bands": raster_bandas,
        },
        "bruto": _asset_objeto(objetos_ref["bruto"], ["source"], "arquivo original enviado", "application/octet-stream"),
        "miniatura": _asset_objeto(objetos_ref["miniatura"], ["thumbnail"], "miniatura 600x400", "image/png"),
    }
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": list(EXTENSOES_STAC),
        "id": item_id,
        "collection": colecao_id,
        "geometry": geometria,
        "bbox": bbox,
        "properties": {
            "datetime": quando,
            "title": titulo,
            "proj:epsg": rel.epsg,
            "proj:shape": [rel.altura, rel.largura],
            "proj:transform": rel.geotransform,
            "plat:perfil": "visual+cientifico",
            "plat:epsg_origem": rel.epsg_origem,
            "plat:nodata": nodata_final,
            "plat:avisos_validacao": rel.avisos,
            "plat:versoes": versoes,
        },
        "assets": assets,
        "links": [],
    }


@tarefa(
    nome="imagens.ingestar",
    descricao="ingere um raster enviado (arquivo): valida, converte para COG visual+científico (rio-cogeo), "
    "sobe ao Garage, cria o item STAC no pgstac e o item raster no catálogo, com miniatura e estatísticas",
    parametros=IngestarParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    perfil_minimo="editor",
    ferramentas=("gdalinfo", "gdal_translate"),
)
def imagens_ingestar(ctx, arquivo_id: uuid.UUID, titulo: str | None = None,
                     epsg_declarado: int | None = None) -> dict:
    inicio = time.monotonic()
    with ctx.db() as cur:
        cur.execute("SELECT id, titulo, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'",
                    (str(arquivo_id),))
        arq = cur.fetchone()
    if arq is None:
        raise FalhaDefinitiva(f"item de arquivo {arquivo_id} inexistente (ou de outro tipo que não 'arquivo')")
    dados_arq = arq["dados"] or {}
    chave_bruto = dados_arq.get("chave")
    if not chave_bruto:
        raise FalhaDefinitiva(f"item de arquivo {arquivo_id} sem chave de objeto no campo dados")
    titulo_final = (titulo or dados_arq.get("nome_original") or arq["titulo"] or "imagem")[:250]

    ctx.progresso(5, "baixando o objeto do armazenamento")
    nome_original = dados_arq.get("nome_original") or "bruto"
    sufixo = ("." + nome_original.rsplit(".", 1)[-1].lower()) if "." in nome_original else ".tif"
    bruto = ctx.dir_trabalho / f"bruto{sufixo}"
    try:
        bytes_baixados = objetos.baixar(chave_bruto, bruto)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise FalhaDefinitiva(f"o objeto do arquivo não existe mais no armazenamento: {e}") from e
    if bytes_baixados > limites.RASTER_BYTES_MAX:
        raise FalhaDefinitiva(
            f"raster de {bytes_baixados} bytes acima do máximo desta instalação ({limites.RASTER_BYTES_MAX})"
        )
    ctx.entrada(arquivo_id, dados_arq.get("sha256") or "", f"bruto {bytes_baixados} bytes")

    ctx.progresso(15, "validando o raster (gdalinfo isolado)")
    try:
        rel = validar(ctx, str(bruto), epsg_declarado=epsg_declarado)
    except RecusaValidacao as e:
        raise FalhaDefinitiva(f"raster recusado ({e.codigo}): {e}") from e
    ctx.log("INFO", f"validação: {rel.largura}x{rel.altura} {rel.bandas} bandas {rel.dtype} EPSG:{rel.epsg} "
            f"({rel.epsg_origem}) driver {rel.driver}")

    ctx.progresso(25, "medindo estatísticas do bruto")
    stats = cog.estatisticas_bruto(bruto, rel)

    ctx.progresso(35, "convertendo o perfil científico (ZSTD)")
    try:
        cientifico = cog.converter_cientifico(ctx, bruto, rel, ctx.dir_trabalho / "cientifico.tif")
        ctx.progresso(60, "convertendo o perfil visual (JPEG/WEBP)")
        visual = cog.converter_visual(ctx, bruto, rel, stats, ctx.dir_trabalho / "visual.tif")
        ctx.progresso(75, "gerando a miniatura")
        mini = cog.miniatura_png(ctx, visual, ctx.dir_trabalho / "miniatura.png")
    except ErroConversao as e:
        # falha determinística do GDAL/rio-cogeo: repetir não conserta — falha definitiva com a causa
        raise FalhaDefinitiva(f"a conversão para COG falhou: {e}") from e
    png600 = miniatura_catalogo.normalizar(mini["caminho"].read_bytes())
    versoes = cog.versoes_software()

    item_id = str(uuid.uuid4())
    # objetos sobem um por transação curta (endereçados por conteúdo: retentativa não duplica)
    ctx.progresso(82, "subindo o COG científico")
    with ctx.db() as cur:
        o_cient = objetos.guardar_arquivo(cur, "raster", cientifico.caminho, "image/tiff", item_id=item_id,
                                          usuario_id=ctx.usuario_id)
    ctx.progresso(88, "subindo o COG visual")
    with ctx.db() as cur:
        o_vis = objetos.guardar_arquivo(cur, "raster", visual.caminho, "image/tiff", item_id=item_id,
                                        usuario_id=ctx.usuario_id)
    ctx.progresso(92, "subindo a miniatura")
    with ctx.db() as cur:
        o_mini = objetos.guardar(cur, "raster", png600, "image/png", item_id=item_id,
                                 usuario_id=ctx.usuario_id)

    geometria, bbox = _geometria_4326(rel)
    objetos_ref = {
        "visual": {**o_vis, "compressao": visual.compressao},
        "cientifico": o_cient,
        "bruto": {"chave": chave_bruto, "sha256": dados_arq.get("sha256") or "", "bytes": bytes_baixados},
        "miniatura": o_mini,
    }
    stac = _item_stac(item_id, ps.nome_colecao(ctx.tenant_id, SLUG_COLECAO), titulo_final, rel, stats,
                      geometria, bbox, objetos_ref, versoes, rel.nodata_final())

    ctx.progresso(96, "gravando o catálogo (STAC + item)")
    dados_item = {
        "colecao": stac["collection"],  # id completo `<tenant_id>-imagens`: inequívoco entre inquilinos
        "stac_id": item_id,
        "perfil": "visual",
        "origem": "copiado",
        "srid_nativo": rel.epsg,
        "bandas": [{"nome": f"banda_{i}"} for i in range(1, rel.bandas + 1)],
    }
    tipos_item.validar("raster", dados_item)
    with ctx.db() as cur:
        colecao_id = _colecao_garantir(cur, ctx.tenant_id)
        ps.item_criar(cur, ctx.tenant_id, colecao_id, stac)
        ri.espelhar(cur, ctx.tenant_id, colecao_id, item_id, {
            "sha256": o_cient["sha256"], "perfil": "visual+cientifico",
            "bytes": o_cient["bytes"] + o_vis["bytes"], "estado": "ativo",
        })
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, criado_por, "
            "modificado_por) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, %s, %s)",
            (item_id, ctx.tenant_id, titulo_final, ctx.usuario_id, jsonb(dados_item),
             o_cient["bytes"] + o_vis["bytes"], ctx.usuario_id, ctx.usuario_id),
        )
        miniatura_catalogo.guardar(cur, item_id, png600)
        try:
            cur.execute("SELECT pgstac.update_collection_extents()")
        except Exception as e:  # extents são derivados; nunca derrubam a ingestão
            ctx.log("AVISO", f"update_collection_extents falhou (extent da coleção ficou mundial): {e}")
    ctx.entrada(item_id, o_cient["sha256"], "COG científico no catálogo")

    duracao = time.monotonic() - inicio
    bytes_cogs = o_cient["bytes"] + o_vis["bytes"]
    taxa = round(bytes_cogs / bytes_baixados, 4) if bytes_baixados else None
    ctx.progresso(100, "concluído")
    return {
        "item_id": item_id,
        "stac_id": item_id,
        "colecao": colecao_id,
        "titulo": titulo_final,
        "duracao_s": round(duracao, 2),
        "bytes_bruto": bytes_baixados,
        "bytes_visual": o_vis["bytes"],
        "bytes_cientifico": o_cient["bytes"],
        "taxa_compressao": taxa,
        "compressao_visual": visual.compressao,
        "sha256_cientifico": o_cient["sha256"],
        "sha256_visual": o_vis["sha256"],
        "epsg": rel.epsg,
        "epsg_origem": rel.epsg_origem,
        "dimensoes": [rel.largura, rel.altura],
        "bandas": rel.bandas,
        "dtype": rel.dtype,
        "avisos_validacao": rel.avisos,
        "versoes": versoes,
    }


__all__ = ["imagens_ingestar", "IngestarParametros"]
