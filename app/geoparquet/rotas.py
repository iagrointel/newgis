"""Rotas do GeoParquet no bucket (item L2-15-a-geoparquet-bucket-catalogo).

    POST   /api/geoparquet                 202 {job_id} — cria/atualiza o GeoParquet de um item (job)
    GET    /api/geoparquet                 lista de jobs do usuário (histórico/auditoria)
    GET    /api/geoparquet/{job_id}        estado do job
    GET    /api/geoparquet/{catalogo_id}/arquivos   URL assinada de curta duração por arquivo (DuckDB/QGIS/Pro)

O item do catálogo resultante (`tipo=parquet`) é lido pela rota genérica `GET /api/itens/{id}` — não há rota
própria para isso (o item já carrega `dados.arquivos[].chave`; só a URL assinada, que expira, é o que este
módulo acrescenta).

Quem pode gerar: privilégio `conteudo.exportar` (mesmo do L0-04-h) + ver o item de origem (RLS: item de outro
inquilino é 404, nunca 403) + ser dono OU ter `conteudo.ver_tudo`/`conteudo.editar_tudo`. Modo `arquivar`
apaga linha da tabela de origem: exige ADEMAIS `conteudo.apagar_tudo` (administrativo)."""

from __future__ import annotations

import psycopg2
from fastapi import APIRouter, Request
from pydantic import Field, field_validator

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import UUID_PADRAO, Modelo
from app.consulta import where_ast
from app.erros import ErroAPI
from app.exportacao.erros import sanear_erro_banco
from app.geoparquet import motor
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["geoparquet"])
GERAR = {"x-auth": "S/T", "x-privilegio": "conteudo.exportar"}
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}


class ParticionarPor(Modelo):
    coluna: str = Field(min_length=1, max_length=63)
    grao: str = Field(default="valor")

    @field_validator("grao")
    @classmethod
    def _grao_ok(cls, v):
        if v not in ("valor", "ano_mes"):
            raise ValueError("grao deve ser 'valor' ou 'ano_mes'")
        return v


class GeoparquetEntrada(Modelo):
    item_id: str = Field(pattern=UUID_PADRAO)
    modo: str = Field(default="exportar")
    where: str | None = Field(default=None, max_length=limites.GEOPARQUET_WHERE_MAX)
    particionar_por: ParticionarPor | None = None
    grupo_linhas: int | None = Field(default=None, ge=limites.GEOPARQUET_GRUPO_LINHAS_MIN,
                                     le=limites.GEOPARQUET_GRUPO_LINHAS_MAX)

    @field_validator("modo")
    @classmethod
    def _modo_ok(cls, v):
        if v not in ("exportar", "arquivar"):
            raise ValueError("modo deve ser 'exportar' ou 'arquivar'")
        return v


def _job_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "item_id": str(r["item_id"]), "modo": r["modo"], "estado": r["estado"],
        "parametros": r["parametros"], "job_id": str(r["job_id"]) if r["job_id"] else None,
        "catalogo_item_id": str(r["catalogo_item_id"]) if r["catalogo_item_id"] else None,
        "versao": r["versao"], "linhas_total": r["linhas_total"], "bytes_total": r["bytes_total"],
        "linhas_arquivadas": r["linhas_arquivadas"], "particoes_alteradas": r["particoes_alteradas"],
        "duracao_ms": r["duracao_ms"], "erro": r["erro"],
        "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
        "concluido_em": r["concluido_em"].isoformat() if r["concluido_em"] else None,
    }


def _pode_gerar_do_item(auth: Auth, item: dict) -> bool:
    if item["dono_id"] == auth.usuario_id:
        return True
    return auth.tem("conteudo.ver_tudo") or auth.tem("conteudo.editar_tudo")


@router.post("/api/geoparquet", status_code=202, openapi_extra=GERAR)
def criar(corpo: GeoparquetEntrada, request: Request, auth: Auth = autenticado("conteudo.exportar")):
    if corpo.modo == "arquivar" and not auth.tem("conteudo.apagar_tudo"):
        raise ErroAPI(403, "arquivar_nao_permitido",
                      "arquivar exige o privilégio conteudo.apagar_tudo (apaga linha da tabela de origem)")
    item_id = uuid_ok(corpo.item_id)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, titulo, dono_id, dados FROM plat.item WHERE id = %s::uuid AND apagado_em IS NULL",
            (item_id,),
        )
        item = cur.fetchone()
        if item is None:
            raise ErroAPI(404, "item_inexistente", "item de origem inexistente")
        if not _pode_gerar_do_item(auth, item):
            raise ErroAPI(403, "geoparquet_nao_permitido", "sem permissão sobre o item de origem")
        dados = item["dados"] or {}
        schema, tabela = dados.get("schema"), dados.get("tabela")
        if not schema or not tabela:
            raise ErroAPI(422, "item_sem_tabela",
                          "o item de origem precisa descrever schema/tabela (dados.schema/dados.tabela)")
        campos_item = [c["nome"] for c in dados.get("campos") or []]
        colunas_brancas = motor.colunas_permitidas(dados.get("campos") or [])
        particionar_por = corpo.particionar_por.model_dump() if corpo.particionar_por else None
        if particionar_por and particionar_por["coluna"] not in colunas_brancas:
            raise ErroAPI(422, "coluna_particao_desconhecida",
                          f"coluna de partição {particionar_por['coluna']!r} não existe no item",
                          {"campos": campos_item})
        geometria = dados.get("geometria", "nenhuma")
        coluna_geom = "geom" if geometria and geometria != "nenhuma" else None
        if corpo.where:
            try:
                sql, _ = motor.montar_select(
                    cur, schema=schema, tabela=tabela, campos=campos_item, coluna_geom=coluna_geom,
                    where=corpo.where, srid_tabela=int(dados.get("srid") or 4326),
                    colunas_brancas=colunas_brancas, particionar_por=None,
                )
            except where_ast.ErroWhere as e:
                raise ErroAPI(400, "where_invalido", e.mensagem, {"codigo": e.codigo, "detalhe": e.detalhe}) from e
            try:
                motor.conferir_where(cur, sql)
            except psycopg2.Error as e:
                mensagem, sqlstate = sanear_erro_banco(e)
                raise ErroAPI(400, "where_invalido", mensagem, {"sqlstate": sqlstate}) from e
        cur.execute("SELECT plat.geoparquet_jobs_em_curso(%s) AS n", (auth.usuario_id,))
        em_curso = int(cur.fetchone()["n"])
        if em_curso >= limites.GEOPARQUET_POR_USUARIO_EM_CURSO:
            raise ErroAPI(429, "geoparquet_jobs_em_curso",
                          f"você já tem {em_curso} job(s) de geoparquet em curso (máximo "
                          f"{limites.GEOPARQUET_POR_USUARIO_EM_CURSO})",
                          {"em_curso": em_curso, "maximo": limites.GEOPARQUET_POR_USUARIO_EM_CURSO})
        parametros = {
            "where": corpo.where, "particionar_por": particionar_por,
            "grupo_linhas": corpo.grupo_linhas or limites.GEOPARQUET_GRUPO_LINHAS_PADRAO,
        }
        cur.execute(
            "INSERT INTO plat.geoparquet_job(tenant_id, usuario_id, item_id, modo, parametros) "
            "VALUES (%s, %s, %s::uuid, %s, %s) RETURNING id",
            (auth.tenant_id, auth.usuario_id, item_id, corpo.modo, jsonb(parametros)),
        )
        job_id = str(cur.fetchone()["id"])
        registrar_evento(cur, request, f"geoparquet/{corpo.modo}_pedido", "item", item_id, {"job_id": job_id})
    job = servico.criar(sessao_de(auth), "geoparquet.gerar", {"job_id": job_id})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.geoparquet_job SET job_id = %s::uuid WHERE id = %s::uuid", (job["id"], job_id))
    return {"job_id": job_id}


@router.get("/api/geoparquet", openapi_extra=LER)
def listar(limite: int = 50, deslocamento: int = 0, item_id: str | None = None,
           auth: Auth = autenticado(escopo_token="catalogo:ler")):
    limite = max(1, min(200, limite))
    deslocamento = max(0, deslocamento)
    condicoes = []
    params: list = []
    if not auth.tem("jobs.gerir_todos"):
        condicoes.append("usuario_id = %s")
        params.append(auth.usuario_id)
    if item_id:
        condicoes.append("item_id = %s::uuid")
        params.append(uuid_ok(item_id))
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.geoparquet_job{onde}", params)
        total = int(cur.fetchone()["n"])
        cur.execute(
            f"SELECT * FROM plat.geoparquet_job{onde} ORDER BY criado_em DESC LIMIT %s OFFSET %s",
            [*params, limite, deslocamento],
        )
        itens = [_job_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens, "limite": limite, "deslocamento": deslocamento}


@router.get("/api/geoparquet/{job_id}", openapi_extra=LER)
def obter(job_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    jid = uuid_ok(job_id, "geoparquet_job_inexistente", "job de geoparquet inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.geoparquet_job WHERE id = %s::uuid", (jid,))
        r = cur.fetchone()
        if r is None or (r["usuario_id"] != auth.usuario_id and not auth.tem("jobs.gerir_todos")):
            raise ErroAPI(404, "geoparquet_job_inexistente", "job de geoparquet inexistente")
        return _job_json(r)


@router.get("/api/geoparquet/{catalogo_item_id}/arquivos", openapi_extra=LER)
def arquivos(catalogo_item_id: str, request: Request,
            auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Um `{chave, sha256, bytes, linhas, bbox, particao, url}` por arquivo do item `parquet`, com URL
    assinada de curta duração (`limites.GEOPARQUET_URL_ASSINADA_SEGUNDOS`) — o mesmo `/api/objetos/{chave}`
    anônimo que qualquer outro arquivo da plataforma usa (ADR 0004 seção 11.2): DuckDB, QGIS e Pro leem
    `https://.../api/objetos/<chave>?ate=...&assinatura=...` como se fosse um Parquet estático."""
    iid = uuid_ok(catalogo_item_id, "item_inexistente", "item inexistente")
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'parquet' AND apagado_em IS NULL",
            (iid,),
        )
        item = cur.fetchone()
        if item is None:
            raise ErroAPI(404, "item_inexistente", "item geoparquet inexistente")
        registrar_evento(cur, request, "geoparquet/arquivos_listados", "item", iid, {})
    base = str(request.base_url).rstrip("/")
    saida = []
    for a in (item["dados"] or {}).get("arquivos") or []:
        url = objetos.url_assinada(a["chave"], limites.GEOPARQUET_URL_ASSINADA_SEGUNDOS)
        saida.append({**a, "url": f"{base}{url}"})
    return {"item_id": iid, "arquivos": saida, "validade_segundos": limites.GEOPARQUET_URL_ASSINADA_SEGUNDOS}
