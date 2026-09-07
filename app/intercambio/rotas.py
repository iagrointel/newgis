"""Rotas do intercâmbio de formatos (item L6-02-o):

- `GET  /api/intercambio/formatos` — o que esta instalação importa e exporta, e o que NÃO temos (com o
  motivo). Resposta "temos / não temos", nunca um total de formatos.
- `POST /api/intercambio/exportacoes` — exporta uma camada (`item_id` + `formato`) ou o inquilino inteiro
  (`tipo: "inquilino"`, escrow GeoPackage + manifesto JSON). Dispara o job correspondente.
- `GET  /api/intercambio/exportacoes[/{id}]` — lista/detalhe (RLS; o usuário comum vê só as dele).
- `GET  /api/intercambio/exportacoes/{id}/baixar` — o pacote gerado (bytes diretos do Garage).
- `DELETE /api/intercambio/exportacoes/{id}` — apaga o registro e o arquivo (dono ou admin).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app import db, objetos
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import jsonb, registrar_evento, uuid_ok
from app.catalogo.modelos import UUID_PADRAO, Modelo
from app.erros import ErroAPI
from app.ingestao.formatos import FORMATOS as FORMATOS_ENTRADA
from app.intercambio.formatos_saida import FORMATOS_SAIDA, NAO_TEMOS
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["intercambio"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
EXPORTAR = {"x-auth": "S", "x-privilegio": "conteudo.exportar"}

TIPOS = ("camada", "inquilino")


class ExportacaoEntrada(Modelo):
    tipo: str = Field(default="camada")
    item_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    formato: str | None = Field(default=None, min_length=1, max_length=40)
    srid: int | None = Field(default=None, ge=1024, le=32767)
    campos: list[str] | None = Field(default=None, max_length=500)
    titulo: str | None = Field(default=None, min_length=1, max_length=120)


def _exportacao_json(r: dict) -> dict:
    return {
        "id": str(r["id"]), "tipo": r["tipo"], "formato": r["formato"],
        "item_origem": str(r["item_origem"]) if r["item_origem"] else None,
        "estado": r["estado"], "avisos": r["avisos"], "relatorio": r["relatorio"], "erro": r["erro"],
        "job_id": str(r["job_id"]) if r["job_id"] else None,
        "item_arquivo": str(r["item_arquivo"]) if r["item_arquivo"] else None,
        "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
    }


def _carregar(cur, auth: Auth, exportacao_id: str) -> dict:
    eid = uuid_ok(exportacao_id, "exportacao_inexistente", "exportação inexistente")
    cur.execute("SELECT * FROM plat.intercambio_exportacao WHERE id = %s::uuid", (eid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "exportacao_inexistente", "exportação inexistente")
    if r["usuario_id"] not in (None, auth.usuario_id) and not auth.tem("conteudo.ver_tudo"):
        raise ErroAPI(404, "exportacao_inexistente", "exportação inexistente")
    return r


@router.get("/api/intercambio/formatos", openapi_extra=LER)
def formatos(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    return {
        "importacao": [
            {"tipo": f.nome, "extensoes": list(f.extensoes), "rotulo": f.rotulo}
            for f in FORMATOS_ENTRADA.values()
        ],
        "exportacao": [
            {"tipo": f.nome, "extensao": f.extensao, "rotulo": f.rotulo,
             "crs_fixo": f.crs_fixo, "geometria": f.geometria,
             "avisos_inerentes": list(f.avisos_inerentes)}
            for f in FORMATOS_SAIDA.values()
        ],
        "nao_temos": list(NAO_TEMOS),
    }


@router.post("/api/intercambio/exportacoes", status_code=202, openapi_extra=EXPORTAR)
def criar(corpo: ExportacaoEntrada, request: Request, auth: Auth = autenticado("conteudo.exportar")):
    if corpo.tipo not in TIPOS:
        raise ErroAPI(422, "tipo_invalido", f"tipo deve ser um de {TIPOS}")
    if corpo.tipo == "camada":
        if not corpo.item_id:
            raise ErroAPI(422, "item_obrigatorio", "o tipo 'camada' exige item_id")
        if not corpo.formato or corpo.formato not in FORMATOS_SAIDA:
            raise ErroAPI(422, "formato_nao_suportado",
                          f"formato {corpo.formato!r} não oferecido; aceitos: {sorted(FORMATOS_SAIDA)}",
                          {"aceitos": sorted(FORMATOS_SAIDA)})
        fmt = FORMATOS_SAIDA[corpo.formato]
        if corpo.srid is not None and fmt.crs_fixo is not None and corpo.srid != fmt.crs_fixo:
            raise ErroAPI(422, "crs_fixo_do_formato",
                          f"o formato {fmt.nome} grava sempre em EPSG:{fmt.crs_fixo}")
        if corpo.srid is not None:
            with db.db(auth.contexto()) as cur:
                cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (corpo.srid,))
                if cur.fetchone() is None:
                    raise ErroAPI(422, "srid_inexistente", f"SRID {corpo.srid} não existe em spatial_ref_sys")
    formato = corpo.formato if corpo.tipo == "camada" else "gpkg+manifesto"
    item_origem = uuid_ok(corpo.item_id) if corpo.item_id else None
    if item_origem:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                "SELECT 1 FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial' "
                "AND apagado_em IS NULL",
                (item_origem,),
            )
            if cur.fetchone() is None:
                raise ErroAPI(404, "camada_inexistente", "camada inexistente")
    parametros = {k: v for k, v in {"srid": corpo.srid, "campos": corpo.campos,
                                    "titulo": corpo.titulo}.items() if v is not None}
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "INSERT INTO plat.intercambio_exportacao(tenant_id, usuario_id, tipo, formato, item_origem, "
            "parametros) VALUES (%s, %s, %s, %s, %s::uuid, %s) RETURNING id",
            (auth.tenant_id, auth.usuario_id, corpo.tipo, formato, item_origem, jsonb(parametros)),
        )
        exportacao_id = str(cur.fetchone()["id"])
        # o evento de auditoria sai no FIM do job (intercambio/exportar_camada|exportar_inquilino em
        # exportar.py), com o resultado — aqui a exportação ainda é só um pedido na fila
    tipo_job = "intercambio.exportar_camada" if corpo.tipo == "camada" else "intercambio.exportar_inquilino"
    job = servico.criar(sessao_de(auth), tipo_job, {"exportacao_id": exportacao_id})
    with db.db(auth.contexto()) as cur:
        cur.execute("UPDATE plat.intercambio_exportacao SET job_id = %s::uuid WHERE id = %s::uuid",
                    (job["id"], exportacao_id))
    return {"exportacao_id": exportacao_id, "job_id": job["id"]}


@router.get("/api/intercambio/exportacoes", openapi_extra=LER)
def listar(limite: int = 50, deslocamento: int = 0, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    limite = max(1, min(200, limite))
    deslocamento = max(0, deslocamento)
    with db.db(auth.contexto()) as cur:
        if auth.tem("conteudo.ver_tudo"):
            cur.execute("SELECT * FROM plat.intercambio_exportacao ORDER BY criado_em DESC "
                        "LIMIT %s OFFSET %s", (limite, deslocamento))
        else:
            cur.execute("SELECT * FROM plat.intercambio_exportacao WHERE usuario_id = %s "
                        "ORDER BY criado_em DESC LIMIT %s OFFSET %s",
                        (auth.usuario_id, limite, deslocamento))
        linhas = cur.fetchall()
    return {"itens": [_exportacao_json(r) for r in linhas], "total": len(linhas)}


@router.get("/api/intercambio/exportacoes/{id}", openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
    return _exportacao_json(r)


@router.get("/api/intercambio/exportacoes/{id}/baixar", openapi_extra=LER,
            responses={200: {"content": {"application/octet-stream": {}}}})
def baixar(id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        if r["estado"] != "concluida" or r["item_arquivo"] is None:
            raise ErroAPI(409, "estado_invalido", f"exportação em estado {r['estado']!r}; nada para baixar")
        cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'",
                    (str(r["item_arquivo"]),))
        arq = cur.fetchone()
        if arq is None:
            raise ErroAPI(404, "objeto_inexistente", "o arquivo da exportação não existe mais")
        registrar_evento(cur, request, "intercambio/baixar", "item", str(r["item_arquivo"]),
                         {"exportacao_id": str(r["id"])})
    try:
        dados = objetos.ler(arq["dados"]["chave"])
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "o arquivo da exportação não existe mais") from e
    nome = (arq["dados"].get("nome_original") or "exportacao.bin").replace('"', "")
    return Response(
        dados,
        media_type=arq["dados"].get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nome}"',
                 "Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.delete("/api/intercambio/exportacoes/{id}", status_code=204, response_class=Response,
               openapi_extra=EXPORTAR)
def apagar(id: str, auth: Auth = autenticado("conteudo.exportar")):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        if r["estado"] in ("fila", "rodando"):
            raise ErroAPI(409, "estado_invalido", f"exportação em estado {r['estado']!r} não pode ser apagada")
        chave = None
        if r["item_arquivo"] is not None:
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (str(r["item_arquivo"]),))
            arq = cur.fetchone()
            chave = (arq["dados"] or {}).get("chave") if arq else None
            cur.execute("DELETE FROM plat.item WHERE id = %s::uuid AND tipo = 'arquivo'",
                        (str(r["item_arquivo"]),))
        cur.execute("DELETE FROM plat.intercambio_exportacao WHERE id = %s::uuid", (str(r["id"]),))
    if chave:
        try:
            objetos.apagar(chave)
        except (FileNotFoundError, objetos.ChaveInvalida):
            pass  # o objeto já não estava no armazenamento; o registro saiu mesmo assim
    return Response(status_code=204)
