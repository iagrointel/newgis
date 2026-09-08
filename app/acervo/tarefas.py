"""Job `acervo.expor_arquivo` (item L6-01-i-raster-e-arquivos): põe UM arquivo do acervo da casa no catálogo do
inquilino, com o sha256 conferido antes de qualquer escrita (`app/acervo/arquivos.py::conferir`).

Duas rotas de exposição, escolhidas pela extensão:
- **raster** (.tif/.tiff/.vrt): item `raster` + item STAC cujo asset aponta para `acervo://<caminho>` — o arquivo
  NÃO é copiado para o balde (guardrail de disco D21: o acervo já ocupa 3,6 GB neste disco; copiar dobraria).
  O ladrilho por token (item L1-02) lê o arquivo local pelo mesmo motor rio-tiler, sem sessão S3.
- **vetor** (.geojson/.gpkg/.shp/.parquet/...): ingestão ÚNICA para PostGIS com `ogr2ogr` na mesma tabela
  `d_<slug>.c_<hash>` que a ingestão do L0-04 usa (`plat.camada_schema_garantir` + `plat.camada_preparar`),
  virando item `camada_vetorial` com `fonte: hospedada`.
Em ambos, a linha de `plat.acervo_arquivo_exposto` guarda o hash CONFERIDO (não o do registro) e o instante.
Item de fonte sem licença escrita (D17) nasce privado e com `uso_restrito: true` em `dados`."""

from __future__ import annotations

import datetime
import json
import uuid

import psycopg2
import psycopg2.extras
from pydantic import BaseModel

from app import limites
from app.acervo import arquivos as arq
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings

SLUG_COLECAO = "acervo"
TIPO_COG = "image/tiff; application=geotiff; profile=cloud-optimized"


class ExporParametros(BaseModel):
    caminho: str
    titulo: str | None = None


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _pg_conninfo() -> str:
    partes = psycopg2.extensions.parse_dsn(settings.PLAT_DSN)
    pares = " ".join(f"{k}={v}" for k, v in partes.items() if k in ("dbname", "host", "port", "user", "password"))
    return f"PG:{pares} application_name=plat-acervo"


def registro_de(cur, caminho: str) -> dict | None:
    cur.execute(
        "SELECT caminho, nome, fonte_id, fonte_nome, orgao, dominio, licenca, frescor, data_dado, "
        "script_gerador, comando_reexecucao, bytes, sha256, feicoes, srid, tipo_geom, extensao, tipo, publicavel "
        "FROM plat.acervo_arquivo WHERE caminho = %s", (caminho,),
    )
    return cur.fetchone()


def _procedencia(r: dict, sha_conferido: str) -> dict:
    return {
        "origem": "acervo", "protocolo": "arquivo", "caminho": r["caminho"], "fonte_id": r["fonte_id"],
        "fonte": r["fonte_nome"], "orgao": r["orgao"], "dominio": r["dominio"], "licenca": r["licenca"],
        "frescor": r["frescor"], "script_gerador": r["script_gerador"],
        "comando_reexecucao": r["comando_reexecucao"], "sha256": sha_conferido,
    }


def _tags(r: dict) -> list[str]:
    """`acervo` + o fonte_id (slug). O DOMÍNIO da fonte não vira tag: o vocabulário do acervo tem vírgula
    ("Empresas, trabalho e renda") e `plat.tags_validas` recusa vírgula em tag."""
    tags = ["acervo"]
    if r.get("fonte_id"):
        tags.append(str(r["fonte_id"])[:128])
    return tags


def _titulo(r: dict, pedido: str | None) -> str:
    base = (pedido or r["nome"] or r["caminho"]).strip()
    return (base[:190] + "…") if len(base) > 195 else base


def _dados_comuns(r: dict, sha: str) -> dict:
    """`uso_restrito` (D17): fonte sem licença escrita — o item existe para a casa, mas compartilhar é recusado."""
    return {"procedencia": _procedencia(r, sha), "uso_restrito": not r["publicavel"]}


def _srid_de(r: dict) -> int:
    bruto = (r.get("srid") or "").strip()
    for parte in bruto.replace(":", " ").split():
        if parte.isdigit():
            return int(parte)
    return 4326


def _expor_raster(ctx, cur, r: dict, a: arq.Arquivo, sha: str, titulo: str, usuario_id: int) -> str:
    from app.imagens import pgstac as ps
    from app.imagens import raster_item as ri

    item_id = str(uuid.uuid4())
    colecao = ps.nome_colecao(ctx.tenant_id, SLUG_COLECAO)
    if ps.colecao_obter(cur, ctx.tenant_id, colecao) is None:
        ps.colecao_criar(cur, ctx.tenant_id, SLUG_COLECAO, {
            "title": "Acervo da casa", "description": "Rasters do acervo da casa expostos por referência (L6-01-i)."})
    info = _info_raster(a)
    asset = {"href": f"acervo://{a.caminho}", "type": TIPO_COG, "roles": ["data"]}
    stac = {
        "type": "Feature", "stac_version": "1.0.0", "id": item_id, "collection": colecao,
        "geometry": info["geometria"], "bbox": info["bbox"],
        "properties": {"datetime": info["datetime"], "title": titulo,
                       "proj:epsg": info["epsg"], "plat:acervo_caminho": a.caminho,
                       "plat:sha256": sha, "plat:fonte_id": r["fonte_id"]},
        "assets": {"cientifico": asset, "visual": dict(asset, roles=["visual"])},
        "links": [],
    }
    ps.item_criar(cur, ctx.tenant_id, colecao, stac)
    ri.espelhar(cur, ctx.tenant_id, colecao, item_id, {
        "sha256": sha, "perfil": "cientifico", "bytes": a.absoluto.stat().st_size, "estado": "ativo"})
    dados = {**_dados_comuns(r, sha), "colecao": colecao, "stac_id": item_id, "perfil": "cientifico",
             "origem": "referenciada", "srid_nativo": info["epsg"],
             "bandas": [{"nome": f"banda_{i}"} for i in range(1, info["bandas"] + 1)]}
    cur.execute(
        "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, acesso, "
        "criado_por, modificado_por, tags) VALUES (%s::uuid, %s, 'raster', %s, %s, %s, %s, 'privado', %s, %s, %s)",
        (item_id, ctx.tenant_id, titulo, usuario_id, _jsonb(dados), a.absoluto.stat().st_size,
         usuario_id, usuario_id, _tags(r)),
    )
    return item_id


def _info_raster(a: arq.Arquivo) -> dict:
    """Extensão, EPSG e nº de bandas lidos do próprio arquivo (rasterio); geometria em 4326 para o STAC."""
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(a.absoluto) as src:
        epsg = src.crs.to_epsg() if src.crs else None
        bandas = src.count
        if epsg:
            oeste, sul, leste, norte = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        else:
            oeste, sul, leste, norte = -180.0, -90.0, 180.0, 90.0
    bbox = [round(oeste, 6), round(sul, 6), round(leste, 6), round(norte, 6)]
    geometria = {"type": "Polygon", "coordinates": [[
        [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]]]]}
    # o instante do dado é o mtime do arquivo: o registro do acervo não tem datetime por arquivo
    mt = datetime.datetime.fromtimestamp(a.absoluto.stat().st_mtime, datetime.UTC)
    return {"bbox": bbox, "geometria": geometria, "epsg": epsg or 4326, "bandas": bandas,
            "datetime": mt.isoformat(timespec="seconds").replace("+00:00", "Z")}


def _expor_vetor(ctx, cur_slug: str, r: dict, a: arq.Arquivo, sha: str, titulo: str, usuario_id: int, ctx_db) -> str:
    """ogr2ogr → `d_<slug>.c_<hash>` (mesma tabela e preparação da ingestão do L0-04)."""
    item_id = str(uuid.uuid4())
    schema = f"d_{cur_slug}"
    tabela = "c_" + uuid.uuid4().hex[:16]
    srid = _srid_de(r)
    with ctx_db() as cur:
        cur.execute("SELECT plat.camada_schema_garantir(%s)", (cur_slug,))
    argv = [
        "ogr2ogr", "-f", "PostgreSQL", _pg_conninfo(), str(a.absoluto),
        "-nln", f"{schema}.{tabela}", "-nlt", "PROMOTE_TO_MULTI",
        "-lco", "GEOMETRY_NAME=geom", "-lco", "FID=fid", "-lco", "FID64=YES",
        "-lco", "SPATIAL_INDEX=NONE", "-lco", "PRECISION=NO", "-lco", "LAUNDER=NO",
        "-a_srs", f"EPSG:{srid}", "--config", "PG_USE_COPY", "YES",
    ]
    ctx.progresso(40, "ogr2ogr")
    res = ctx.subprocesso(argv)
    if res.returncode != 0:
        linhas = [ln for ln in (res.stderr or "").splitlines() if ln.strip()]
        raise FalhaDefinitiva(f"ogr2ogr falhou: {(linhas[-1] if linhas else 'sem detalhe')[:200]}")
    with ctx_db() as cur:
        cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)", (schema, tabela, srid, "Geometry", usuario_id))
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{tabela}"')
        n = cur.fetchone()["n"]
        cur.execute(
            "SELECT type FROM geometry_columns WHERE f_table_schema=%s AND f_table_name=%s "
            "AND f_geometry_column='geom'", (schema, tabela),
        )
        linha_geom = cur.fetchone()
        cur.execute(
            "SELECT column_name AS nome, data_type AS tipo FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s AND column_name NOT IN "
            "('fid','geom','globalid','versao','tenant_id','criado_em','atualizado_em','criado_por','atualizado_por') "
            "ORDER BY ordinal_position", (schema, tabela),
        )
        campos = [{"nome": c["nome"], "tipo": c["tipo"]} for c in cur.fetchall()]
        dados = {**_dados_comuns(r, sha), "schema": schema, "tabela": tabela,
                 "geometria": (linha_geom or {}).get("type") or "Geometry", "srid": srid,
                 "campos": campos, "fonte": "hospedada", "edicao": {"habilitada": False},
                 "estatisticas": {"feicoes": n}}
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, "
            "modificado_por, tags) VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, 'privado', %s, %s, %s)",
            (item_id, ctx.tenant_id, titulo, usuario_id, _jsonb(dados), usuario_id, usuario_id, _tags(r)),
        )
    return item_id


@tarefa(
    nome="acervo.expor_arquivo",
    descricao="Expõe um arquivo do acervo da casa no catálogo (sha256 conferido; raster por referência, vetor "
              "ingerido uma vez para PostGIS)",
    parametros=ExporParametros, pesado=False, memoria_mb=1024, timeout_s=3600, tentativas=1,
    chave=lambda p: f"acervo.expor:{p.get('caminho')}", perfil_minimo="editor", versao=1,
)
def acervo_expor_arquivo(ctx, caminho: str, titulo: str | None = None) -> dict:
    if not arq.configurado():
        raise FalhaDefinitiva("esta instalação não tem raiz de arquivos do acervo configurada")
    with ctx.db() as cur:
        r = registro_de(cur, caminho)
        if r is None:
            raise FalhaDefinitiva(f"caminho {caminho!r} não está no registro do acervo")
        cur.execute("SELECT id FROM plat.usuario WHERE id = %s", (ctx.usuario_id,))
        dono = cur.fetchone()
        usuario_id = dono["id"] if dono else None
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        slug = cur.fetchone()["slug"]
        cur.execute("SELECT item_id::text AS item_id, tipo, sha256_conferido, bytes, publicavel "
                    "FROM plat.acervo_arquivo_exposto WHERE caminho = %s", (caminho,))
        ja = cur.fetchone()
    if ja:
        # idempotente: o mesmo caminho exposto duas vezes devolve o item que já existe, no MESMO formato
        return {"caminho": caminho, "item_id": ja["item_id"], "tipo": ja["tipo"], "sha256": ja["sha256_conferido"],
                "publicavel": bool(ja["publicavel"]), "bytes": ja["bytes"], "ja_exposto": True,
                "teto_bytes": limites.ACERVO_ARQUIVO_BYTES_MAX}
    if usuario_id is None:
        raise FalhaDefinitiva("job sem usuário dono: a exposição precisa de um autor")
    ctx.progresso(10, "conferindo sha256")
    try:
        a = arq.conferir(dict(r))
    except arq.ArquivoRecusado as e:
        with ctx.db() as cur:
            motivo = json.dumps({"caminho": caminho, "erro": e.erro}, ensure_ascii=False)
            cur.execute("SELECT plat.evento_registrar(%s, 'item', NULL, %s::jsonb, NULL, NULL)",
                        ("acervo/arquivo_recusar", motivo))
        raise FalhaDefinitiva(f"arquivo recusado ({e.erro}): {e.mensagem}") from e
    sha = a.sha256_registro  # conferir() só devolve quando o hash do disco é igual a este
    titulo_final = _titulo(dict(r), titulo)
    ctx.progresso(30, f"expondo {a.tipo}")
    if a.tipo == "raster":
        with ctx.db() as cur:
            item_id = _expor_raster(ctx, cur, dict(r), a, sha, titulo_final, usuario_id)
    else:
        item_id = _expor_vetor(ctx, slug, dict(r), a, sha, titulo_final, usuario_id, ctx.db)
    with ctx.db() as cur:
        cur.execute(
            "INSERT INTO plat.acervo_arquivo_exposto(tenant_id, caminho, item_id, tipo, sha256_registro, "
            "sha256_conferido, bytes, publicavel, exposto_por) "
            "VALUES (plat.tenant_atual(), %s, %s::uuid, %s, %s, %s, %s, %s, %s)",
            (caminho, item_id, a.tipo, sha, sha, a.absoluto.stat().st_size, bool(r["publicavel"]), usuario_id),
        )
        cur.execute(
            "SELECT plat.evento_registrar(%s, 'item', %s, %s::jsonb, NULL, NULL)",
            ("acervo/arquivo_expor", item_id,
             json.dumps({"caminho": caminho, "tipo": a.tipo, "sha256": sha, "fonte_id": r["fonte_id"],
                         "publicavel": bool(r["publicavel"])}, ensure_ascii=False)),
        )
    ctx.progresso(100, "exposto")
    return {"caminho": caminho, "item_id": item_id, "tipo": a.tipo, "sha256": sha,
            "publicavel": bool(r["publicavel"]), "bytes": a.absoluto.stat().st_size,
            "teto_bytes": limites.ACERVO_ARQUIVO_BYTES_MAX}
