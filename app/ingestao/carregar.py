"""Job `ingestao.carregar` (ADR 0005 seção 6, L0-04-c): `ogr2ogr` como neto do job (RLIMIT_DATA/OPENBLAS já
aplicados pelo `app/jobs/filho.py`) para `d_<slug>.c_<uuid16>`, `ST_MakeValid` com relatório, colunas obrigatórias +
RLS FORCE + índices por `plat.camada_preparar()`, estatísticas e item de catálogo `camada_vetorial` com
proveniência. Falha ou cancelamento em qualquer passo derruba a tabela e o item (nunca sobra órfão dos dois
lados — invariante testada em `tests/api/ingestao/test_ingestao.py::test_cota_excedida_nao_cria_tabela`; teste
de morte do worker (SIGKILL) fica para o L0-04-c completo, ver handoff do item)."""

from __future__ import annotations

import hashlib
import json
import uuid

import psycopg2.extensions
import psycopg2.extras
from pydantic import BaseModel

from app import limites, objetos
from app.ingestao import georreferencia
from app.ingestao.inspecionar import PREPARADORES, _cfg, tabela_de
from app.jobs.registro import Cancelado, FalhaDefinitiva, tarefa
from app.settings import settings

CARGA_FATOR_COTA = limites.CARGA_FATOR_COTA
FIDS_RELATORIO_MAX = limites.INGESTAO_FIDS_RELATORIO_MAX


class CarregarParametros(BaseModel):
    importacao_id: uuid.UUID


def _jsonb(valor):
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


def _pg_conninfo() -> str:
    """`PG:...` para o `ogr2ogr` a partir de PLAT_DSN (o mesmo `plat_app` do pool da API; ADR 0005 seção 6.1:
    'ogr2ogr conecta como plat_app')."""
    partes = psycopg2.extensions.parse_dsn(settings.PLAT_DSN)
    pares = " ".join(f"{k}={v}" for k, v in partes.items() if k in ("dbname", "host", "port", "user", "password"))
    return f"PG:{pares} application_name=plat-ingestao"


def _marcar_falha(ctx, importacao_id: str, erro: str) -> None:
    with ctx.db() as cur:
        cur.execute(
            "UPDATE plat.importacao SET estado = %s, erro = %s, atualizado_em = now() "
            "WHERE id = %s::uuid AND estado NOT IN ('concluida','falhou','cancelada','expirada')",
            ("cancelada" if "cancel" in erro.lower() else "falhou", erro[:2000], importacao_id),
        )


def _limpar_orfao(ctx, schema: str, tabela: str, item_id: str) -> None:
    with ctx.db() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')
        cur.execute("DELETE FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,))


def _select_campos(prep: dict, campos: list[dict]) -> tuple[str, list[dict]]:
    """`SELECT "<origem>" AS <nome>, …` só dos campos marcados `importar` (padrão True); devolve também a lista
    final (para o relatório de campos não importados/renomeados)."""
    partes = []
    usados_finais = []
    for c in campos:
        if c.get("importar", True) is False:
            continue
        origem_sql = c["nome"] if prep.get("origem_e_normalizada") else c["origem"]
        partes.append(f'"{origem_sql}" AS {c["nome"]}')
        usados_finais.append(c)
    if not partes:
        raise FalhaDefinitiva("nenhum campo selecionado para importar")
    return ", ".join(partes), usados_finais


@tarefa(
    nome="ingestao.carregar",
    descricao="Carrega o arquivo confirmado como tabela PostGIS do inquilino (ogr2ogr + ST_MakeValid + RLS)",
    parametros=CarregarParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: f"importacao:{p.get('importacao_id')}",
    perfil_minimo="editor",
    ferramentas=("gdal",),
)
def ingestao_carregar(ctx, importacao_id: uuid.UUID) -> dict:
    iid = str(importacao_id)
    with ctx.db() as cur:
        cur.execute("SELECT * FROM plat.importacao WHERE id = %s::uuid", (iid,))
        imp = cur.fetchone()
        if imp is None:
            raise FalhaDefinitiva("importação inexistente")
        if imp["estado"] != "confirmada":
            raise FalhaDefinitiva(f"importação em estado {imp['estado']!r}; esperava 'confirmada'")
        cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (imp["arquivo_id"],))
        arq = cur.fetchone()
        if arq is None:
            raise FalhaDefinitiva("o arquivo de origem não existe mais")
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        slug = cur.fetchone()["slug"]

    schema = f"d_{slug}"
    proposta = imp["proposta"] or {}
    confirmacao = imp["confirmacao"] or {}
    tabela = proposta.get("nome_tabela") or tabela_de(imp["item_id"])
    item_id = str(imp["item_id"])
    formato = imp["formato"]
    reservado = 0
    tabela_criada = False

    try:
        with ctx.db() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{tabela}" CASCADE')  # passo 0: limpeza defensiva
            cur.execute("DELETE FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,))
            cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))

        ctx.progresso(5, "baixando o arquivo")
        dados = objetos.ler(arq["dados"]["chave"])
        sha_real = hashlib.sha256(dados).hexdigest()
        if sha_real != arq["dados"]["sha256"]:
            raise FalhaDefinitiva("arquivo corrompido: sha256 divergente do gravado no upload")
        ctx.entrada(imp["arquivo_id"], sha_real, "arquivo de origem")

        estimativa = max(len(dados) * CARGA_FATOR_COTA, 1024 * 1024)
        with ctx.db() as cur:
            cur.execute(
                "SELECT cota_bytes, uso_bytes, uso_reservado_bytes FROM plat.tenant WHERE id = %s FOR UPDATE",
                (ctx.tenant_id,),
            )
            t = cur.fetchone()
            if t["uso_bytes"] + t["uso_reservado_bytes"] + estimativa > t["cota_bytes"]:
                faltam = (t["uso_bytes"] + t["uso_reservado_bytes"] + estimativa - t["cota_bytes"]) // (1024 * 1024)
                raise FalhaDefinitiva(f"cota do inquilino excedida: faltam {faltam} MB")
            cur.execute(
                "UPDATE plat.tenant SET uso_reservado_bytes = uso_reservado_bytes + %s WHERE id = %s",
                (estimativa, ctx.tenant_id),
            )
            reservado = estimativa

        ctx.progresso(15, "preparando a fonte")
        encoding_confirmada = ((confirmacao.get("codificacao") or {}).get("valor")
                               or proposta.get("codificacao", {}).get("valor"))
        respostas_cad = {k: v for k, v in (confirmacao.get("cad") or {}).items() if v is not None}
        if formato in ("dxf", "dwg"):
            prep = PREPARADORES[formato](ctx, dados, encoding_confirmada, respostas_cad)
        else:
            prep = PREPARADORES[formato](ctx, dados, encoding_confirmada)

        srid = int((confirmacao.get("crs") or {}).get("srid") or proposta.get("crs", {}).get("srid") or 0)
        if not srid:
            raise FalhaDefinitiva("CRS não confirmado: SRID ausente")

        campos = confirmacao.get("campos") or proposta.get("campos") or []
        select_sql, campos_usados = _select_campos(prep, campos)
        geom = confirmacao.get("geometria") or proposta.get("geometria") or {}
        tipo_escolhido_raw = geom.get("escolhida") or "Geometry"  # o que a inspeção/usuário resolveu
        camada_origem = proposta.get("camada_origem") or prep.get("layer")
        sql_origem = f'SELECT {select_sql} FROM "{camada_origem}"'
        # DXF/DWG: o usuário escolhe QUAIS camadas do desenho entram (a lista veio na proposta). Sem escolha,
        # entram todas — nunca um recorte silencioso.
        camadas_escolhidas = respostas_cad.get("camadas") if formato in ("dxf", "dwg") else None
        if camadas_escolhidas:
            disponiveis = set(proposta.get("camadas_desenho") or [])
            desconhecidas = [c for c in camadas_escolhidas if c not in disponiveis]
            if desconhecidas:
                raise FalhaDefinitiva(
                    f"camada do desenho que não existe na proposta: {desconhecidas[0][:80]}")
            lista = ", ".join("'" + c.replace("'", "''") + "'" for c in camadas_escolhidas)
            sql_origem += f" WHERE Layer IN ({lista})"

        # PROMOTE_TO_MULTI (e não o tipo singular): ST_MakeValid pode fragmentar um Polygon/LineString
        # inválido em várias partes (MEDIDO com dado real: buraco tocando o contorno em cobertura do solo de
        # Guarulhos gera MultiPolygon de uma tabela cuja origem era 100% Polygon) — coluna criada singular
        # (`geometry(Polygon,…)`) recusaria esse UPDATE com "Geometry type (MultiPolygon) does not match
        # column type (Polygon)". PROMOTE_TO_MULTI cria sempre a coluna Multi* para as famílias que podem
        # fragmentar; "Geometry" (genérico, geometria mista) não promove — a coluna fica solta de propósito.
        nlt = "GEOMETRY" if tipo_escolhido_raw == "Geometry" else "PROMOTE_TO_MULTI"

        oo_args = []
        for o in prep.get("oo", []):
            oo_args += ["-oo", o]
        argv = [
            "ogr2ogr", "-f", "PostgreSQL", _pg_conninfo(),
            *_cfg(prep.get("config")),
            *oo_args,
            prep["caminho"],
            "-nln", f"{schema}.{tabela}", "-nlt", nlt,
            "-lco", "GEOMETRY_NAME=geom", "-lco", "FID=fid", "-lco", "FID64=YES",
            "-lco", "SPATIAL_INDEX=NONE", "-lco", "PRECISION=NO", "-lco", "LAUNDER=NO",
            "-a_srs", f"EPSG:{srid}",
            "-dialect", "OGRSQL", "-sql", sql_origem,
            "--config", "PG_USE_COPY", "YES",
        ]
        ctx.progresso(25, "ogr2ogr")
        r = ctx.subprocesso(argv)
        if r.returncode != 0:
            linhas = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            raise FalhaDefinitiva(f"ogr2ogr falhou: {(linhas[-1] if linhas else 'sem detalhe')[:200]}")
        tabela_criada = True

        # tipo REAL da coluna criada (autoridade é o banco, não a proposta: PROMOTE_TO_MULTI decide sozinho)
        with ctx.db() as cur:
            cur.execute(
                "SELECT type FROM geometry_columns WHERE f_table_schema=%s AND f_table_name=%s "
                "AND f_geometry_column='geom'", (schema, tabela),
            )
            r_tipo = cur.fetchone()
        mapa_tipo = {"POINT": "Point", "MULTIPOINT": "MultiPoint", "LINESTRING": "LineString",
                     "MULTILINESTRING": "MultiLineString", "POLYGON": "Polygon", "MULTIPOLYGON": "MultiPolygon",
                     "GEOMETRY": "Geometry", "GEOMETRYCOLLECTION": "Geometry"}
        tipo_escolhido_raw = mapa_tipo.get((r_tipo["type"] if r_tipo else "").upper(), tipo_escolhido_raw)
        tipo_escolhido_nlt = tipo_escolhido_raw.upper()

        # ------------------------------------------------------------ georreferência do desenho (CAD)
        # O DXF vem em coordenada de desenho. A semelhança 2D ajustada nos pontos de controle (ou, na falta
        # deles, a escala da unidade declarada) é aplicada AQUI, na tabela já carregada, com `ST_Affine` — o
        # desenho original não é reescrito. O RMSE do ajuste vai para o relatório da importação.
        georref = None
        if formato in ("dxf", "dwg"):
            pedido = respostas_cad.get("georreferencia") or {}
            pontos = pedido.get("pontos") or []
            if pontos:
                origem = [(float(p["desenho"][0]), float(p["desenho"][1])) for p in pontos]
                destino = [(float(p["terreno"][0]), float(p["terreno"][1])) for p in pontos]
                try:
                    georref = georreferencia.ajustar(origem, destino)
                except (georreferencia.PontosInsuficientes, georreferencia.AjusteImpossivel) as e:
                    raise FalhaDefinitiva(f"georreferência recusada: {e}") from e
                georref["origem"] = "pontos_de_controle"
            else:
                unidade = ((proposta.get("cad") or {}).get("unidade") or {})
                metros = respostas_cad.get("metros_por_unidade") or unidade.get("metros_por_unidade")
                georref = georreferencia.escala_de_unidade(metros)
                if georref:
                    georref["origem"] = "unidade_declarada"
            if georref:
                ctx.progresso(40, "aplicando a georreferência")
                with ctx.db() as cur:
                    cur.execute(f'UPDATE "{schema}"."{tabela}" SET geom = '
                                f'{georreferencia.sql_geometria(georref)} WHERE geom IS NOT NULL')

        # ------------------------------------------------------------ validade (ST_MakeValid)
        ctx.progresso(45, "validando geometria")
        acao = (confirmacao.get("validade") or {}).get("acao") or proposta.get("validade", {}).get("acao") or "corrigir"
        relatorio = {"corrigidas": 0, "descartadas": 0, "fids_corrigidos": []}
        if tipo_escolhido_nlt != "GEOMETRY":
            with ctx.db() as cur:
                cur.execute(
                    f'SELECT count(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalidas, count(*) AS total '
                    f'FROM "{schema}"."{tabela}"'
                )
                r_val = cur.fetchone()
                if r_val["invalidas"]:
                    if acao == "recusar":
                        raise FalhaDefinitiva(f"{r_val['invalidas']} geometrias inválidas; carga recusada pelo usuário")
                    if acao == "descartar":
                        cur.execute(f'DELETE FROM "{schema}"."{tabela}" WHERE NOT ST_IsValid(geom)')
                        relatorio["descartadas"] = int(r_val["invalidas"])
                    else:
                        cur.execute(
                            f'SELECT fid FROM "{schema}"."{tabela}" WHERE NOT ST_IsValid(geom) '
                            f'LIMIT {FIDS_RELATORIO_MAX}'
                        )
                        relatorio["fids_corrigidos"] = [row["fid"] for row in cur.fetchall()]
                        dim = {"Point": 1, "MultiPoint": 1, "LineString": 2, "MultiLineString": 2,
                               "Polygon": 3, "MultiPolygon": 3}.get(tipo_escolhido_raw, 3)
                        # ST_ReducePrecision ANTES de ST_MakeValid quebra em geometria já inválida (GEOS lança
                        # TopologyException tentando arredondar coordenadas de um polígono que já não fecha
                        # direito — MEDIDO com dado real: buraco tocando o contorno em duas feições de
                        # cobertura do solo de Guarulhos). A ordem certa é validar primeiro, reduzir precisão
                        # do resultado (já válido) depois — o `ST_MakeValid` sozinho já resolve a autointerseção
                        # e o anel não fechado; o `ST_ReducePrecision` final só remove ruído de ponto flutuante.
                        cur.execute(
                            f'UPDATE "{schema}"."{tabela}" SET geom = '
                            f'ST_Multi(ST_CollectionExtract(ST_ReducePrecision(ST_MakeValid(geom), 1e-9), {dim})) '
                            f'WHERE NOT ST_IsValid(geom)'
                        )
                        cur.execute(f'DELETE FROM "{schema}"."{tabela}" WHERE geom IS NOT NULL AND ST_IsEmpty(geom)')
                        relatorio["corrigidas"] = int(r_val["invalidas"])

        # ------------------------------------------------------------ colunas obrigatórias, RLS, índices, gatilhos
        ctx.progresso(60, "preparando a tabela (RLS, índices, gatilhos)")
        with ctx.db() as cur:
            cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)",
                        (schema, tabela, srid, tipo_escolhido_raw, ctx.usuario_id))

        # ------------------------------------------------------------ estatísticas
        ctx.progresso(80, "estatísticas")
        with ctx.db() as cur:
            cur.execute(f'ANALYZE "{schema}"."{tabela}"')
            cur.execute(
                f'SELECT count(*) AS feicoes, '
                f'ST_AsGeoJSON(ST_Transform(ST_SetSRID(ST_Extent(geom)::geometry, {srid}), 4326)) AS extent_geojson '
                f'FROM "{schema}"."{tabela}"'
            )
            est = cur.fetchone()
            extent_4326 = None
            if est["extent_geojson"]:
                coords = json.loads(est["extent_geojson"])["coordinates"][0]
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                if -180 <= min(xs) and max(xs) <= 180 and -90 <= min(ys) and max(ys) <= 90:
                    extent_4326 = [min(xs), min(ys), max(xs), max(ys)]
            por_campo = {}
            for c in campos_usados:
                if c["tipo"] in ("text",):
                    cur.execute(
                        f'SELECT count(*) FILTER (WHERE {c["nome"]} IS NULL) AS nulos, '
                        f'count(DISTINCT {c["nome"]}) AS distintos, max(length({c["nome"]})) AS max_len '
                        f'FROM "{schema}"."{tabela}"'
                    )
                else:
                    cur.execute(
                        f'SELECT count(*) FILTER (WHERE {c["nome"]} IS NULL) AS nulos, '
                        f'count(DISTINCT {c["nome"]}) AS distintos, min({c["nome"]}) AS minimo, '
                        f'max({c["nome"]}) AS maximo '
                        f'FROM "{schema}"."{tabela}"'
                    )
                por_campo[c["nome"]] = {k: v for k, v in cur.fetchone().items()}
            cur.execute('SELECT pg_total_relation_size(%s::regclass) AS b', (f'"{schema}"."{tabela}"',))
            tamanho_bytes = int(cur.fetchone()["b"])

        # ------------------------------------------------------------ item de catálogo + relação + evento
        ctx.progresso(90, "publicando no catálogo")
        estatisticas = {
            "feicoes": int(est["feicoes"]), "extent_nativo": extent_4326, "por_campo": por_campo,
            "calculadas_em": None,
        }
        procedencia = {
            "fonte": (arq["dados"] or {}).get("nome_original"), "url": None, "licenca": None,
            "data_do_dado": None, "data_de_acesso": None, "gerador": "plat ingestao.carregar v1",
            "sha256": sha_real, "metodo": "ogr2ogr + ST_MakeValid", "confianca": None,
            "limites": proposta.get("avisos", []), "job_id": str(ctx.job_id), "importacao_id": iid,
        }
        item_dados = {
            "schema": schema, "tabela": tabela, "geometria": tipo_escolhido_raw,
            "srid": srid,
            "campos": [{"nome": c["nome"], "tipo": c["tipo"], "alias": c.get("origem", c["nome"])}
                       for c in campos_usados],
            "fonte": "hospedada", "procedencia": procedencia,
            "estatisticas": estatisticas,
            "importacao": {"importacao_id": iid, "job_id": str(ctx.job_id), "relatorio": relatorio},
        }
        if formato in ("dxf", "dwg"):
            item_dados["cad"] = {"desenho": (proposta.get("cad") or {}).get("totais"),
                                 "versao": (proposta.get("cad") or {}).get("versao"),
                                 "unidade": (proposta.get("cad") or {}).get("unidade"),
                                 "camadas_importadas": camadas_escolhidas or proposta.get("camadas_desenho"),
                                 "georreferencia": georref}
            relatorio["georreferencia"] = georref
        titulo = (confirmacao.get("titulo") or proposta.get("titulo") or "camada")[:250]
        with ctx.db() as cur:
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, tamanho_bytes, "
                "extent, extent_origem, criado_por, modificado_por) "
                "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, "
                + ("ST_MakeEnvelope(%s,%s,%s,%s,4326)" if extent_4326 else "NULL") + ", %s, %s, %s)",
                [item_id, ctx.tenant_id, titulo, ctx.usuario_id, _jsonb(item_dados), tamanho_bytes]
                + (extent_4326 if extent_4326 else [])
                + (["dado"] if extent_4326 else [None])
                + [ctx.usuario_id, ctx.usuario_id],
            )
            cur.execute(
                "INSERT INTO plat.item_relacao(origem, destino, tipo, tenant_id) VALUES (%s::uuid, %s::uuid, "
                "'arquivo_de_camada', %s) ON CONFLICT DO NOTHING",
                (imp["arquivo_id"], item_id, ctx.tenant_id),
            )
            cur.execute(
                "UPDATE plat.tenant SET uso_reservado_bytes = greatest(0, uso_reservado_bytes - %s), "
                "uso_bytes = uso_bytes + %s WHERE id = %s",
                (reservado, tamanho_bytes, ctx.tenant_id),
            )
            cur.execute(
                "UPDATE plat.importacao SET estado = 'concluida', relatorio = %s, item_id = %s::uuid, "
                "atualizado_em = now() WHERE id = %s::uuid",
                (_jsonb(relatorio | {"feicoes_carregadas": int(est["feicoes"])}), item_id, iid),
            )
            cur.execute(
                "SELECT plat.evento_registrar('camadas/importar', 'item', %s, %s::jsonb, NULL, NULL)",
                (item_id, json.dumps({"formato": formato, "job_id": str(ctx.job_id)}, default=str)),
            )
        ctx.progresso(100, "concluído")
        return {"item_id": item_id, "feicoes": int(est["feicoes"]), "corrigidas": relatorio["corrigidas"],
                "descartadas": relatorio["descartadas"], "avisos": proposta.get("avisos", []),
                "rmse": (relatorio.get("georreferencia") or {}).get("rmse")}
    except Cancelado:
        if tabela_criada:
            _limpar_orfao(ctx, schema, tabela, item_id)
        if reservado:
            with ctx.db() as cur:
                cur.execute("UPDATE plat.tenant SET uso_reservado_bytes = greatest(0, uso_reservado_bytes - %s) "
                            "WHERE id = %s", (reservado, ctx.tenant_id))
        _marcar_falha(ctx, iid, "cancelamento solicitado")
        raise
    except FalhaDefinitiva as e:
        if tabela_criada:
            _limpar_orfao(ctx, schema, tabela, item_id)
        if reservado:
            with ctx.db() as cur:
                cur.execute("UPDATE plat.tenant SET uso_reservado_bytes = greatest(0, uso_reservado_bytes - %s) "
                            "WHERE id = %s", (reservado, ctx.tenant_id))
        _marcar_falha(ctx, iid, str(e))
        raise
