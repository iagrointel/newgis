"""Job `geoparquet.gerar` (item L2-15-a-geoparquet-bucket-catalogo): lê a camada/tabela sob a RLS do
inquilino, escreve GeoParquet (particionado ou não) no diretório de trabalho do job, envia cada arquivo ao
Garage em partes e publica/atualiza UM item de catálogo tipo `parquet` — ao contrário da exportação comum
(L0-04-h), este item NÃO expira: é o formato de trabalho para o grande, feito para ser reaberto por DuckDB/
QGIS/Pro várias vezes.

Duas rodadas sobre a MESMA origem (mesmo `item_id` + mesma partição) são a mesma "fonte": a 2ª rodada acha o
`geoparquet_job` anterior em estado `pronta`, herda o `catalogo_item_id` (o item do catálogo não é recriado,
é ATUALIZADO) e a `versao` sobe em 1. Cada partição é comparada por sha256 com a rodada anterior — como
`objetos.guardar_arquivo` já deduplica por conteúdo (a chave É o sha256), a partição sem mudança nunca gera
um PUT novo no bucket; só a lista `particoes_alteradas` deste job muda de uma rodada para outra.

Modo `arquivar`: além de gerar o(s) arquivo(s), apaga da tabela de origem as linhas exportadas — DEPOIS de
conferir que a contagem lida do Parquet bate com o `DELETE ... RETURNING` da mesma condição (mesmo `where`/
partição), na MESMA transação. Se não bater, a transação não commita e nada é apagado (a linha do job registra
`falhou`, nunca uma contagem inventada).
"""

from __future__ import annotations

import datetime
import json
import sys
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
from pydantic import BaseModel

from app import limites, objetos
from app.consulta import where_ast
from app.geoparquet import motor
from app.jobs.registro import Cancelado, FalhaDefinitiva, tarefa

CLASSE_OBJETO = "geoparquet"
TIPO_ITEM_CATALOGO = "parquet"


class GerarParametros(BaseModel):
    job_id: uuid.UUID


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _marcar_falha(ctx, job_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.geoparquet_job SET estado = %s, erro = %s, concluido_em = now() "
            "WHERE id = %s::uuid AND estado NOT IN ('pronta','falhou','cancelada')",
            ("cancelada" if "cancel" in erro.lower() else "falhou", erro[:2000], job_id),
        )


def _resolver_origem(dados: dict) -> tuple[str, str, list[dict], int, str | None]:
    """`(schema, tabela, campos, srid, coluna_geom)` a partir do `dados` de QUALQUER item que descreva uma
    tabela (camada_vetorial, ou outro tipo que siga a mesma convenção `schema`/`tabela`/`campos`/`srid`/
    `geometria` — histórico de fluxo e acervo assinado, quando existirem, entram aqui sem mudar este job)."""
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not schema or not tabela:
        raise FalhaDefinitiva("o item de origem não descreve schema/tabela (dados.schema/dados.tabela ausentes)")
    campos = [c["nome"] for c in dados.get("campos") or []]
    if not campos:
        raise FalhaDefinitiva("o item de origem não tem campos declarados")
    srid = int(dados.get("srid") or 4326)
    geometria = dados.get("geometria", "nenhuma")
    coluna_geom = "geom" if geometria and geometria != "nenhuma" else None
    return schema, tabela, campos, srid, coluna_geom


def _job_anterior(cur, item_id: str, particionar_por: dict | None) -> dict | None:
    cur.execute(
        "SELECT * FROM plat.geoparquet_job WHERE item_id = %s::uuid AND modo = 'exportar' AND estado = 'pronta' "
        "ORDER BY criado_em DESC LIMIT 20",
        (item_id,),
    )
    alvo = json.dumps(particionar_por or None, sort_keys=True)
    for r in cur.fetchall():
        if json.dumps((r["parametros"] or {}).get("particionar_por"), sort_keys=True) == alvo:
            return r
    return None


def _chave_particao(particao: dict) -> str:
    return json.dumps(particao or {}, sort_keys=True)


@tarefa(
    nome="geoparquet.gerar",
    descricao="Exporta camada/tabela para GeoParquet (particionado ou não) e publica/atualiza item do catálogo",
    parametros=GerarParametros,
    pesado=True,
    memoria_mb=limites.GEOPARQUET_MEMORIA_MB,
    timeout_s=limites.GEOPARQUET_TIMEOUT_S,
    tentativas=1,
    chave=lambda p: f"geoparquet:{p.get('job_id')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def geoparquet_gerar(ctx, job_id: uuid.UUID) -> dict:
    jid = str(job_id)
    trabalho = Path(ctx.dir_trabalho)
    gerados: list[Path] = []
    try:
        with ctx.db() as cur:
            cur.execute("SELECT * FROM plat.geoparquet_job WHERE id = %s::uuid", (jid,))
            job = cur.fetchone()
            if job is None:
                raise FalhaDefinitiva("job de geoparquet inexistente")
            if job["estado"] != "pendente":
                raise FalhaDefinitiva(f"job em estado {job['estado']!r}; esperava 'pendente'")
            cur.execute(
                "SELECT id, titulo, dados, tipo FROM plat.item WHERE id = %s::uuid", (str(job["item_id"]),)
            )
            item = cur.fetchone()
            if item is None:
                raise FalhaDefinitiva("o item de origem não existe mais")
            cur.execute("UPDATE plat.geoparquet_job SET estado = 'gerando' WHERE id = %s::uuid", (jid,))
            anterior = _job_anterior(cur, str(job["item_id"]), (job["parametros"] or {}).get("particionar_por"))

        p = job["parametros"] or {}
        schema, tabela, campos_item, srid, coluna_geom = _resolver_origem(item["dados"] or {})
        colunas_brancas = motor.colunas_permitidas((item["dados"] or {}).get("campos") or [])
        particionar_por = p.get("particionar_por")
        grupo_linhas = int(p.get("grupo_linhas") or limites.GEOPARQUET_GRUPO_LINHAS_PADRAO)

        # ---------------------------------------------------------------- disco antes de qualquer byte
        with ctx.db() as cur:
            cur.execute("SELECT pg_total_relation_size(%s::regclass) AS b", (f'"{schema}"."{tabela}"',))
            tamanho_tabela = int(cur.fetchone()["b"])
        estimativa = max(tamanho_tabela * limites.GEOPARQUET_FATOR_DISCO, 8 * 1024 * 1024)
        motor.exigir_disco(trabalho, estimativa)
        ctx.log("INFO", f"tabela de {tamanho_tabela // 1024} KB; livre agora: "
                        f"{motor.espaco_livre(trabalho) // (1024 * 1024)} MB")

        # ---------------------------------------------------------------- consulta
        ctx.progresso(5, "montando a consulta")
        with ctx.db() as cur:
            try:
                sql, colunas_particao = motor.montar_select(
                    cur, schema=schema, tabela=tabela, campos=campos_item, coluna_geom=coluna_geom,
                    where=p.get("where"), srid_tabela=srid, colunas_brancas=colunas_brancas,
                    particionar_por=particionar_por,
                )
            except where_ast.ErroWhere as e:
                raise FalhaDefinitiva(f"filtro inválido: {e.mensagem}") from e
            except motor.ErroGeoparquet as e:
                raise FalhaDefinitiva(str(e)) from e

        # ---------------------------------------------------------------- ogr2ogr (GPKG intermediário)
        ctx.progresso(15, "extraindo do banco (GPKG intermediário)")
        intermediario = trabalho / "intermediario.gpkg"
        gerados.append(intermediario)
        argv = motor.argumentos_ogr2ogr_gpkg(
            destino=intermediario, conninfo=motor.conninfo_pg(ctx.tenant_id, ctx.usuario_id), sql=sql,
            nome_camada="dados",
        )
        (resultado, ms_ogr) = motor.cronometrar(ctx.subprocesso, argv)
        if resultado.returncode != 0:
            avisos = [ln.strip() for ln in (resultado.stderr or "").splitlines() if ln.strip()]
            raise FalhaDefinitiva(f"ogr2ogr falhou: {(avisos[-1] if avisos else 'sem detalhe')[:300]}")
        if not intermediario.exists():
            raise FalhaDefinitiva("ogr2ogr terminou sem escrever o arquivo (consulta sem nenhuma linha?)")

        # ---------------------------------------------------------------- DuckDB: particiona e sela 1.1.0
        ctx.progresso(40, "convertendo para GeoParquet")
        saida_dir = trabalho / "saida"
        gerados.append(saida_dir)
        argv_duck = [sys.executable, "-m", "app.geoparquet.duckdb_cli", "particionar", str(intermediario),
                    str(saida_dir), str(limites.GEOPARQUET_MEMORIA_MB), colunas_particao or "-",
                    str(grupo_linhas)]
        (resultado, ms_duck) = motor.cronometrar(ctx.subprocesso, argv_duck, cwd=str(motor.RAIZ))
        if resultado.returncode != 0:
            detalhe = [ln for ln in (resultado.stderr or "").splitlines() if ln.strip()]
            raise FalhaDefinitiva(f"GeoParquet: {(detalhe[-1] if detalhe else 'sem detalhe')[:300]}")
        manifesto = None
        for linha in reversed((resultado.stdout or "").splitlines()):
            if linha.strip().startswith("{"):
                manifesto = json.loads(linha)
                break
        if manifesto is None:
            raise FalhaDefinitiva("GeoParquet: o conversor não devolveu o manifesto")

        ctx.verificar()

        # ---------------------------------------------------------------- envio ao bucket (dedup por sha256)
        ctx.progresso(65, f"enviando {len(manifesto['arquivos'])} arquivo(s) ao bucket")
        catalogo_item_id = str(anterior["catalogo_item_id"]) if anterior and anterior["catalogo_item_id"] else \
            str(uuid.uuid4())
        anterior_por_particao = {}
        if anterior:
            for a in anterior["arquivos"] or []:
                anterior_por_particao[_chave_particao(a.get("particao"))] = a
        arquivos_finais = []
        particoes_alteradas = []
        with ctx.db() as cur:
            for a in manifesto["arquivos"]:
                caminho_local = saida_dir / a["caminho"]
                chave_p = _chave_particao(a.get("particao"))
                anterior_arq = anterior_por_particao.get(chave_p)
                era_conhecido = objetos.existe(anterior_arq["chave"]) if anterior_arq else False
                if anterior_arq and anterior_arq["sha256"] == a["sha256"] and era_conhecido:
                    novo = False
                else:
                    novo = True
                    particoes_alteradas.append(a.get("particao") or {})
                objeto = objetos.guardar_arquivo(
                    cur, CLASSE_OBJETO, caminho_local, "application/vnd.apache.parquet",
                    item_id=catalogo_item_id, usuario_id=ctx.usuario_id, extensao=".parquet",
                )
                arquivos_finais.append({
                    "chave": objeto["chave"], "sha256": objeto["sha256"], "bytes": objeto["bytes"],
                    "linhas": a["linhas"], "bbox": a.get("bbox"), "particao": a.get("particao") or {},
                    "novo": novo,
                })

        linhas_total = int(manifesto["linhas_total"])
        bytes_total = sum(a["bytes"] for a in arquivos_finais)
        versao = int(anterior["versao"]) + 1 if anterior and anterior["versao"] else 1

        # ---------------------------------------------------------------- modo arquivar: expurgo conferido
        linhas_arquivadas = None
        if job["modo"] == "arquivar":
            ctx.progresso(85, "conferindo e apagando as linhas de origem")
            with ctx.db() as cur:
                delete_sql = f'DELETE FROM "{schema}"."{tabela}"'
                params: list = []
                if p.get("where"):
                    consulta = where_ast.compilar_where(p["where"], colunas_brancas)
                    delete_sql += f" WHERE ({consulta.sql})"
                    params = consulta.params
                cur.execute(delete_sql, params)
                apagadas = cur.rowcount
                if apagadas != linhas_total:
                    # a exceção sai do `with ctx.db()` e o context manager dá ROLLBACK da transação inteira
                    # (app/db.py: "commit no fim, rollback em exceção") — o DELETE acima nunca chega a valer
                    raise FalhaDefinitiva(
                        f"expurgo recusado: {apagadas} linha(s) apagada(s) na origem != {linhas_total} "
                        "linha(s) no GeoParquet gerado — nada foi apagado"
                    )
                cur.execute("SELECT plat.geoparquet_arquivar_confirmar(%s::uuid, %s)", (jid, apagadas))
                linhas_arquivadas = apagadas

        # ---------------------------------------------------------------- item do catálogo (publica/atualiza)
        ctx.progresso(95, "publicando o item do catálogo")
        esquema_saida = [c for c in manifesto["esquema"] if c["nome"] not in ("_geoparquet_ano", "_geoparquet_mes")]
        item_dados = {
            "origem": {"item_id": str(item["id"]), "tipo_item": item["tipo"], "schema": schema, "tabela": tabela},
            "particionar_por": particionar_por,
            "grupo_linhas": grupo_linhas,
            "crs": srid,
            "esquema": esquema_saida,
            "arquivos": arquivos_finais,
            "linhas_total": linhas_total,
            "bytes_total": bytes_total,
            "proveniencia": {
                "item_id": str(item["id"]), "versao": versao,
                "gerado_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "modo": job["modo"], "job_id": jid,
                **({"linhas_arquivadas": linhas_arquivadas} if linhas_arquivadas is not None else {}),
            },
        }
        titulo = f"{item['titulo']} (GeoParquet)"
        with ctx.db() as cur:
            if anterior and anterior["catalogo_item_id"]:
                cur.execute(
                    "UPDATE plat.item SET dados = %s, tamanho_bytes = %s, modificado_por = %s, "
                    "modificado_em = now() WHERE id = %s::uuid RETURNING id",
                    (_jsonb(item_dados), bytes_total, ctx.usuario_id, catalogo_item_id),
                )
                r = cur.fetchone()
                if r is None:  # o item do catálogo foi apagado por fora: recria com o MESMO id
                    cur.execute(
                        "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                        "criado_por, modificado_por) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (catalogo_item_id, ctx.tenant_id, TIPO_ITEM_CATALOGO, titulo[:250], ctx.usuario_id,
                         _jsonb(item_dados), bytes_total, ctx.usuario_id, ctx.usuario_id),
                    )
            else:
                cur.execute(
                    "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                    "criado_por, modificado_por) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (catalogo_item_id, ctx.tenant_id, TIPO_ITEM_CATALOGO, titulo[:250], ctx.usuario_id,
                     _jsonb(item_dados), bytes_total, ctx.usuario_id, ctx.usuario_id),
                )
            cur.execute(
                "UPDATE plat.geoparquet_job SET estado = 'pronta', catalogo_item_id = %s::uuid, versao = %s, "
                "arquivos = %s, particoes_alteradas = %s, linhas_total = %s, bytes_total = %s, "
                "duracao_ms = %s, concluido_em = now() WHERE id = %s::uuid",
                (catalogo_item_id, versao, _jsonb(arquivos_finais), _jsonb(particoes_alteradas), linhas_total,
                 bytes_total, ms_ogr + ms_duck, jid),
            )
            evento_tipo = "geoparquet/arquivar" if job["modo"] == "arquivar" else "geoparquet/gerar"
            cur.execute(
                "SELECT plat.evento_registrar(%s, 'item', %s, %s::jsonb, NULL, NULL)",
                (evento_tipo, str(job["item_id"]),
                 json.dumps({"job_id": jid, "catalogo_item_id": catalogo_item_id, "versao": versao,
                            "linhas_total": linhas_total, "bytes_total": bytes_total}, default=str)),
            )
        ctx.progresso(100, "concluído")
        return {
            "job_id": jid, "catalogo_item_id": catalogo_item_id, "versao": versao, "linhas_total": linhas_total,
            "bytes_total": bytes_total, "arquivos": len(arquivos_finais),
            "particoes_alteradas": particoes_alteradas, "linhas_arquivadas": linhas_arquivadas,
            "duracao_ogr2ogr_ms": ms_ogr, "duracao_duckdb_ms": ms_duck,
        }
    except Cancelado:
        _marcar_falha(ctx, jid, "cancelamento solicitado")
        raise
    except FalhaDefinitiva as e:
        _marcar_falha(ctx, jid, str(e))
        raise
    except (psycopg2.Error, OSError) as e:
        _marcar_falha(ctx, jid, str(e)[:500])
        raise FalhaDefinitiva(str(e)[:500]) from e
    finally:
        for caminho in gerados:
            motor.limpar(caminho)
