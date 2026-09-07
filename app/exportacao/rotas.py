"""Rotas da exportação de camada (item L0-04-h-exportar; ADR 0018).

    GET    /api/exportacoes/formatos      o que a tela do botão Exportar desenha (11 formatos)
    POST   /api/exportacoes               202 {exportacao_id, job_id} — valida TUDO antes de enfileirar
    GET    /api/exportacoes               lista do usuário (admin vê a do inquilino)
    GET    /api/exportacoes/{id}          estado, relatório e link de download
    GET    /api/exportacoes/{id}/baixar   o arquivo, em blocos (nunca inteiro em memória)
    DELETE /api/exportacoes/{id}          cancela a pendente ou apaga o arquivo pronto

Quem pode exportar (as três condições, nesta ordem):
1. privilégio `conteudo.exportar` (perfis editor e admin por padrão) — sem ele, 403 antes de qualquer coisa;
2. enxergar o item (RLS de `plat.item`: item de outro inquilino é 404, nunca 403 — não se confirma a
   existência de conteúdo alheio);
3. ser o dono do item, ou ter `conteudo.ver_tudo`/`conteudo.editar_tudo` (admin), ou o dono ter ligado
   `dados.exportacao.permitir_outros` — que nasce DESLIGADO, como o "Allow others to export to different
   formats" da Esri. Senão, 403 `exportacao_nao_permitida`.

O filtro `where` é conferido AQUI, contra o banco, antes de existir job: `where_ast` recusa o que é
sintaticamente inválido ou usa campo fora da lista branca (400 `where_invalido`), e um `LIMIT 0` no banco pega
o que só o banco sabe (tipo incompatível, função inexistente) — 400 com o erro do banco SANEADO
(`app/exportacao/erros.py`). Assim o usuário recebe o erro na hora, e não um job que falha 3 s depois.
"""

from __future__ import annotations

import psycopg2
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import UUID_PADRAO, Modelo
from app.consulta import where_ast
from app.erros import ErroAPI
from app.exportacao import motor
from app.exportacao.erros import sanear_erro_banco
from app.exportacao.formatos import descrever as descrever_formatos
from app.exportacao.formatos import obter as formato_de
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["exportacao"])
EXPORTAR = {"x-auth": "S/T", "x-privilegio": "conteudo.exportar"}
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
ESTADOS_APAGAVEIS = ("pendente", "gerando")


class OpcoesCsv(Modelo):
    separador: str = Field(default=",")
    decimal: str = Field(default=".")
    coluna_x: str | None = Field(default=None, max_length=63)
    coluna_y: str | None = Field(default=None, max_length=63)

    @field_validator("separador")
    @classmethod
    def _sep(cls, v):
        if v not in limites.EXPORTACAO_CSV_SEPARADORES:
            raise ValueError(f"separador deve ser um de {limites.EXPORTACAO_CSV_SEPARADORES!r}")
        return v

    @field_validator("decimal")
    @classmethod
    def _dec(cls, v):
        if v not in limites.EXPORTACAO_CSV_DECIMAIS:
            raise ValueError("decimal deve ser '.' ou ','")
        return v


class ExportacaoEntrada(Modelo):
    item_id: str = Field(pattern=UUID_PADRAO)
    formato: str = Field(min_length=1, max_length=40)
    nome: str | None = Field(default=None, max_length=limites.EXPORTACAO_NOME_MAX)
    campos: list[str] | None = Field(default=None, max_length=limites.EXPORTACAO_CAMPOS_MAX)
    where: str | None = Field(default=None, max_length=limites.EXPORTACAO_WHERE_MAX)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    srid_saida: int | None = Field(default=None, ge=1, le=999999)
    codificacao: str | None = Field(default=None, max_length=20)
    pasta_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    csv: OpcoesCsv | None = None


def _exportacao_json(r: dict, base_url: str = "") -> dict:
    pronta = r["estado"] == "pronta"
    return {
        "id": str(r["id"]), "item_id": str(r["item_id"]), "formato": r["formato"], "estado": r["estado"],
        "parametros": r["parametros"], "job_id": str(r["job_id"]) if r["job_id"] else None,
        "arquivo_item_id": str(r["arquivo_item_id"]) if r["arquivo_item_id"] else None,
        "sha256": r["sha256"], "bytes": r["bytes"], "feicoes": r["feicoes"], "duracao_ms": r["duracao_ms"],
        "erro": r["erro"],
        "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
        "concluido_em": r["concluido_em"].isoformat() if r["concluido_em"] else None,
        "expira_em": r["expira_em"].isoformat() if r["expira_em"] else None,
        "link": f"{base_url}/api/exportacoes/{r['id']}/baixar" if pronta else None,
        "validade_dias": limites.EXPORTACAO_VALIDADE_DIAS,
    }


def _carregar(cur, auth: Auth, exportacao_id: str) -> dict:
    eid = uuid_ok(exportacao_id, "exportacao_inexistente", "exportação inexistente")
    cur.execute("SELECT * FROM plat.exportacao WHERE id = %s::uuid", (eid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "exportacao_inexistente", "exportação inexistente")
    if r["usuario_id"] != auth.usuario_id and not auth.tem("jobs.gerir_todos"):
        raise ErroAPI(404, "exportacao_inexistente", "exportação inexistente")
    return r


def _pode_exportar_o_item(auth: Auth, item: dict) -> bool:
    if item["dono_id"] == auth.usuario_id:
        return True
    if auth.tem("conteudo.ver_tudo") or auth.tem("conteudo.editar_tudo"):
        return True
    return bool(((item["dados"] or {}).get("exportacao") or {}).get("permitir_outros"))


@router.get("/api/exportacoes/formatos", openapi_extra=LER)
def formatos(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    return {"formatos": descrever_formatos(), "validade_dias": limites.EXPORTACAO_VALIDADE_DIAS,
            "em_curso_max": limites.EXPORTACAO_POR_USUARIO_EM_CURSO}


@router.post("/api/exportacoes", status_code=202, openapi_extra=EXPORTAR)
def criar(corpo: ExportacaoEntrada, request: Request, auth: Auth = autenticado("conteudo.exportar")):
    formato = formato_de(corpo.formato)
    if formato is None:
        raise ErroAPI(422, "formato_nao_suportado",
                      f"formato {corpo.formato!r} não suportado; aceitos: {list(descrever_formatos_nomes())}",
                      {"aceitos": list(descrever_formatos_nomes())})
    codificacao = (corpo.codificacao or "UTF-8").upper()
    if codificacao not in formato.codificacoes:
        raise ErroAPI(422, "codificacao_nao_suportada",
                      f"{formato.rotulo} só grava em {', '.join(formato.codificacoes)}",
                      {"aceitas": list(formato.codificacoes)})
    item_id = uuid_ok(corpo.item_id)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT id, titulo, dono_id, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial' "
            "AND apagado_em IS NULL", (item_id,),
        )
        item = cur.fetchone()
        if item is None:
            raise ErroAPI(404, "item_inexistente", "camada inexistente")
        if not _pode_exportar_o_item(auth, item):
            raise ErroAPI(403, "exportacao_nao_permitida",
                          "o dono desta camada não permitiu que outros a exportem")
        dados = item["dados"] or {}
        if dados.get("fonte") != "hospedada":
            raise ErroAPI(422, "camada_nao_hospedada",
                          "só camada hospedada (tabela do inquilino) é exportável nesta versão")
        campos_item = [c["nome"] for c in dados.get("campos") or []]
        desconhecidos = [c for c in (corpo.campos or []) if c not in campos_item]
        if desconhecidos:
            raise ErroAPI(422, "campo_desconhecido", f"campos que não existem na camada: {desconhecidos}",
                          {"campos": desconhecidos})
        if corpo.srid_saida:
            cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (corpo.srid_saida,))
            if cur.fetchone() is None:
                raise ErroAPI(422, "srid_desconhecido",
                              f"EPSG:{corpo.srid_saida} não existe nesta instalação do PostGIS",
                              {"srid": corpo.srid_saida})
        # filtro: sintaxe/lista branca aqui, semântica no banco (LIMIT 0) — os dois ANTES de criar o job
        if corpo.where or corpo.bbox:
            try:
                sql = motor.montar_select(
                    cur, schema=dados["schema"], tabela=dados["tabela"],
                    campos=(corpo.campos or campos_item), coluna_geom="geom", where=corpo.where,
                    bbox=corpo.bbox, srid_tabela=int(dados.get("srid") or 4326),
                    colunas_brancas=motor.colunas_permitidas(dados.get("campos") or []),
                )
            except where_ast.ErroWhere as e:
                raise ErroAPI(400, "where_invalido", e.mensagem, {"codigo": e.codigo, "detalhe": e.detalhe}) from e
            try:
                motor.conferir_where(cur, sql)
            except psycopg2.Error as e:
                mensagem, sqlstate = sanear_erro_banco(e)
                raise ErroAPI(400, "where_invalido", mensagem, {"sqlstate": sqlstate}) from e
        cur.execute("SELECT plat.exportacoes_em_curso(%s) AS n", (auth.usuario_id,))
        em_curso = int(cur.fetchone()["n"])
        if em_curso >= limites.EXPORTACAO_POR_USUARIO_EM_CURSO:
            raise ErroAPI(429, "exportacoes_em_curso",
                          f"você já tem {em_curso} exportações em curso (máximo "
                          f"{limites.EXPORTACAO_POR_USUARIO_EM_CURSO}); espere uma terminar",
                          {"em_curso": em_curso, "maximo": limites.EXPORTACAO_POR_USUARIO_EM_CURSO})
        parametros = {
            "nome": corpo.nome, "campos": corpo.campos, "where": corpo.where, "bbox": corpo.bbox,
            "srid_saida": corpo.srid_saida, "codificacao": codificacao, "pasta_id": corpo.pasta_id,
            "csv": corpo.csv.model_dump() if corpo.csv else None,
        }
        cur.execute(
            "INSERT INTO plat.exportacao(tenant_id, usuario_id, item_id, formato, parametros) "
            "VALUES (%s, %s, %s::uuid, %s, %s) RETURNING id",
            (auth.tenant_id, auth.usuario_id, item_id, formato.nome, jsonb(parametros)),
        )
        exportacao_id = str(cur.fetchone()["id"])
        registrar_evento(cur, request, "camadas/exportar", "item", item_id,
                         {"exportacao_id": exportacao_id, "formato": formato.nome})
    job = servico.criar(sessao_de(auth), "exportacao.gerar", {"exportacao_id": exportacao_id})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.exportacao SET job_id = %s::uuid WHERE id = %s::uuid",
                    (job["id"], exportacao_id))
    return {"exportacao_id": exportacao_id, "job_id": job["id"]}


def descrever_formatos_nomes():
    return [f["nome"] for f in descrever_formatos()]


@router.get("/api/exportacoes", openapi_extra=LER)
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
        cur.execute(f"SELECT count(*) AS n FROM plat.exportacao{onde}", params)
        total = int(cur.fetchone()["n"])
        cur.execute(
            f"SELECT * FROM plat.exportacao{onde} ORDER BY criado_em DESC LIMIT %s OFFSET %s",
            [*params, limite, deslocamento],
        )
        itens = [_exportacao_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens, "limite": limite, "deslocamento": deslocamento}


@router.get("/api/exportacoes/{exportacao_id}", openapi_extra=LER)
def obter(exportacao_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return _exportacao_json(_carregar(cur, auth, exportacao_id))


@router.get("/api/exportacoes/{exportacao_id}/baixar", openapi_extra=LER,
            responses={200: {"content": {"application/octet-stream": {}}}})
def baixar(exportacao_id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Entrega o arquivo em blocos (`objetos.ler_stream`), nunca lendo o objeto inteiro para a memória: uma
    exportação de camada grande passa fácil de 1 GB e este processo atende outras requisições ao mesmo tempo."""
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, exportacao_id)
        if r["estado"] == "expirada" or (r["estado"] == "pronta" and not r["chave"]):
            raise ErroAPI(410, "exportacao_expirada",
                          f"o arquivo desta exportação expirou (validade de {limites.EXPORTACAO_VALIDADE_DIAS} "
                          "dias) e foi apagado")
        if r["estado"] != "pronta":
            raise ErroAPI(409, "exportacao_nao_pronta", f"a exportação está em estado {r['estado']!r}")
        cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (str(r["arquivo_item_id"]),))
        arq = cur.fetchone()
        registrar_evento(cur, request, "camadas/exportar_baixar", "item", str(r["item_id"]),
                         {"exportacao_id": str(r["id"])})
    nome = ((arq or {}).get("dados") or {}).get("nome_original") or f"exportacao{r['formato']}"
    tipo = ((arq or {}).get("dados") or {}).get("content_type") or "application/octet-stream"
    try:
        blocos = objetos.ler_stream(r["chave"])
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(410, "exportacao_expirada", "o arquivo desta exportação já não está no armazenamento") from e
    return StreamingResponse(
        blocos,
        media_type=tipo,
        headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
            "Content-Length": str(r["bytes"]),
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


@router.delete("/api/exportacoes/{exportacao_id}", status_code=204, response_class=Response, openapi_extra=LER)
def apagar(exportacao_id: str, auth: Auth = autenticado(escopo_token="admin:inquilino")):
    """Cancela a que ainda roda (o job é cancelado junto) ou apaga o arquivo da que já está pronta."""
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, exportacao_id)
    if r["estado"] in ESTADOS_APAGAVEIS:
        if r["job_id"]:
            try:
                servico.cancelar(sessao_de(auth), str(r["job_id"]))
            except Exception:  # noqa: BLE001, S110 — job já terminado ou inexistente não impede marcar aqui
                pass
        with db.db(auth.contexto()) as cur:
            cur.execute(
                "UPDATE plat.exportacao SET estado = 'cancelada', concluido_em = now() "
                "WHERE id = %s::uuid AND estado IN ('pendente','gerando')", (str(r["id"]),),
            )
        return Response(status_code=204)
    if r["chave"]:
        objetos.apagar(r["chave"])
    with db.db(auth.contexto()) as cur:
        if r["arquivo_item_id"]:
            cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (str(r["arquivo_item_id"]),))
            cur.execute("SELECT plat.item_expurgar(%s::uuid)", (str(r["arquivo_item_id"]),))
        cur.execute(
            "UPDATE plat.exportacao SET estado = 'expirada', chave = NULL, arquivo_item_id = NULL "
            "WHERE id = %s::uuid AND estado = 'pronta'", (str(r["id"]),),
        )
    return Response(status_code=204)
