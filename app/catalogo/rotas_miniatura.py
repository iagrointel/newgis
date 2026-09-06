"""Rotas de miniatura (ADR 0004 seção 11): GET entrega (204 sem miniatura, ETag), POST envia (JSON base64: o CSRF sob
cookie exige application/json; multipart entra com o L0-11), POST /gerar enfileira o job catalogo.miniatura, DELETE
limpa. Miniatura não entra em item_versao."""

from fastapi import APIRouter, Request, Response

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum, miniatura
from app.catalogo.comum import exigir_edicao, item_ou_404, registrar_evento, uuid_ok
from app.catalogo.modelos import JobCriado, Miniatura, MiniaturaEntrada
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(tags=["catalogo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}


@router.get("/api/itens/{id}/miniatura", openapi_extra=LER, responses={200: {"content": {"image/png": {}}}, 204: {}})
def ver_miniatura(id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        r = item_ou_404(cur, id)
    return miniatura.entregar(r, request)


@router.post(
    "/api/itens/{id}/miniatura",
    response_model=Miniatura,
    openapi_extra={"x-auth": "S", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"},
)
def enviar_miniatura(id: str, corpo: MiniaturaEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    # o acesso vem ANTES de olhar o conteúdo: quem não enxerga o item recebe 404, nunca 415 sobre o formato da imagem
    with db.db(auth.contexto()) as cur:
        exigir_edicao(cur, iid)
    dados = miniatura.decodificar_base64(corpo.conteudo)
    png = miniatura.normalizar(dados)
    with db.db(auth.contexto()) as cur:
        exigir_edicao(cur, iid)
        o = miniatura.guardar(cur, iid, png)
        detalhe = {"acao": "enviar", "sha256": o["sha256"], "bytes": o["bytes"]}
        registrar_evento(cur, request, "itens/miniatura", "item", iid, detalhe)
    return {"miniatura": f"/api/itens/{iid}/miniatura", "sha256": o["sha256"]}


@router.post("/api/itens/{id}/miniatura/gerar", response_model=JobCriado, status_code=202, openapi_extra=EDITAR)
def gerar_miniatura(id: str, request: Request, auth: Auth = autenticado("jobs.executar")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        r = exigir_edicao(cur, iid)
        if r["tipo"] not in miniatura.GERADORES:
            raise ErroAPI(
                409,
                "tipo_sem_gerador",
                f"o tipo {r['tipo']} ainda não tem gerador de miniatura",
                {"tipo": r["tipo"], "geradores": sorted(miniatura.GERADORES)},
            )
    job = servico.criar(sessao_de(auth), "catalogo.miniatura", {"item_id": iid})
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "itens/miniatura", "item", iid, {"acao": "gerar", "job_id": job["id"]})
    return {"job_id": job["id"]}


@router.delete("/api/itens/{id}/miniatura", status_code=204, response_class=Response, openapi_extra=EDITAR)
def apagar_miniatura(id: str, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        r = exigir_edicao(cur, iid)
        if r["miniatura_chave"]:
            cur.execute(
                "UPDATE plat.item SET miniatura_chave = NULL, miniatura_sha256 = NULL WHERE id = %s::uuid", (iid,)
            )
            registrar_evento(cur, request, "itens/miniatura", "item", iid, {"acao": "remover"})
    return Response(status_code=204)


__all__ = ["router", "comum"]
