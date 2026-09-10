"""Rotas de pacote e de galeria de modelos (item L5-37-pacotes-modelos-entre-inquilinos).

`GET /api/itens/{id}/pacote` baixa o zip; `POST /api/pacotes/verificar` diz, ANTES de escrever qualquer
coisa, o que falta mapear e onde o esquema não bate campo a campo; `POST /api/pacotes/importar` cria os
documentos com ids novos. `/api/modelos` é a galeria: publicar, listar, baixar e apagar um pacote guardado.
O zip trafega em base64 dentro de JSON (mesma razão da miniatura, ADR 0004 seção 11: CSRF sob cookie exige
application/json)."""

import base64
import binascii

from fastapi import APIRouter, Request, Response

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import pacote
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import AnalisePacote, ImportacaoPacote, ModeloEntrada, ModeloGaleria, PacoteEntrada
from app.erros import ErroAPI

router = APIRouter(tags=["catalogo"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
IMPORTAR = {"x-auth": "S", "x-privilegio": "conteudo.criar"}
ZIP = {"Cache-Control": "no-store"}


def _bytes_do_corpo(cur, corpo, auth) -> bytes:
    """O zip vem em base64 (`conteudo`) ou de um modelo da galeria (`modelo_id`); exatamente um dos dois."""
    if bool(corpo.conteudo) == bool(corpo.modelo_id):
        raise ErroAPI(422, "entrada_invalida", "informe `conteudo` (base64) ou `modelo_id`, nunca os dois")
    if corpo.modelo_id:
        return bytes(pacote.modelo_ou_404(cur, uuid_ok(corpo.modelo_id, "modelo_inexistente", "modelo inexistente"))[
            "conteudo"
        ])
    try:
        return base64.b64decode(corpo.conteudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErroAPI(422, "entrada_invalida", "`conteudo` não é base64 válido") from e


@router.get("/api/itens/{id}/pacote", openapi_extra=LER, responses={200: {"content": {"application/zip": {}}}})
def exportar_pacote(id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Zip com o documento, tudo de que ele depende e as fontes DECLARADAS (sem dado)."""
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        conteudo, manifesto = pacote.montar(cur, iid, auth.tenant_slug)
        registrar_evento(
            cur,
            request,
            "pacotes/exportar",
            "item",
            iid,
            {
                "documentos": len(manifesto["documentos"]),
                "fontes": len(manifesto["fontes"]),
                "sha256_conteudo": manifesto["sha256_conteudo"],
            },
        )
    return Response(
        conteudo,
        media_type="application/zip",
        headers={**ZIP, "Content-Disposition": f'attachment; filename="pacote-{iid}.zip"'},
    )


@router.post("/api/pacotes/verificar", response_model=AnalisePacote, openapi_extra=IMPORTAR)
def verificar_pacote(corpo: PacoteEntrada, auth: Auth = autenticado("conteudo.criar", so_sessao=True)):
    """Não escreve nada: lista os documentos, as fontes e, para cada fonte já mapeada, a diferença de
    esquema campo a campo. `pronto` só é verdadeiro quando a importação passaria."""
    with db.db(auth.contexto()) as cur:
        manifesto, _ = pacote.ler(_bytes_do_corpo(cur, corpo, auth))
        return pacote.analisar(cur, manifesto, corpo.mapeamento)


@router.post("/api/pacotes/importar", response_model=ImportacaoPacote, status_code=201, openapi_extra=IMPORTAR)
def importar_pacote(corpo: PacoteEntrada, request: Request, auth: Auth = autenticado("conteudo.criar", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        manifesto, documentos = pacote.ler(_bytes_do_corpo(cur, corpo, auth))
        return pacote.importar(cur, request, auth, manifesto, documentos, corpo.mapeamento, corpo.pasta_id)


# ---------------------------------------------------------------- galeria de modelos
@router.get("/api/modelos", response_model=list[ModeloGaleria], openapi_extra=LER)
def listar_modelos(escopo: str | None = None, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Modelos do próprio inquilino e os de escopo `plataforma` (a política de linha da tabela é quem
    decide; a rota não filtra por inquilino à mão)."""
    if escopo not in (None, "inquilino", "plataforma"):
        raise ErroAPI(422, "entrada_invalida", "escopo é `inquilino` ou `plataforma`")
    with db.db(auth.contexto()) as cur:
        return pacote.listar_modelos(cur, auth.tenant_id, escopo)


@router.post("/api/modelos", response_model=ModeloGaleria, status_code=201, openapi_extra=IMPORTAR)
def publicar_modelo(corpo: ModeloEntrada, request: Request, auth: Auth = autenticado("conteudo.criar", so_sessao=True)):
    """Publica um pacote na galeria: `conteudo` em base64, ou `item_id` para exportar e publicar de uma vez.
    Escopo `plataforma` (visível a todos os inquilinos) só passa se quem chama for superadmin — quem recusa
    é a política da tabela, não um `if` da rota."""
    if bool(corpo.conteudo) == bool(corpo.item_id):
        raise ErroAPI(422, "entrada_invalida", "informe `conteudo` (base64) ou `item_id`, nunca os dois")
    with db.db(auth.contexto()) as cur:
        if corpo.item_id:
            conteudo, _ = pacote.montar(cur, uuid_ok(corpo.item_id), auth.tenant_slug)
        else:
            try:
                conteudo = base64.b64decode(corpo.conteudo, validate=True)
            except (binascii.Error, ValueError) as e:
                raise ErroAPI(422, "entrada_invalida", "`conteudo` não é base64 válido") from e
        try:
            return pacote.publicar_modelo(cur, request, auth, corpo.nome, corpo.descricao, corpo.escopo, conteudo)
        except db.psycopg2.errors.InsufficientPrivilege as e:  # política de linha: escopo plataforma sem superadmin
            raise ErroAPI(403, "sem_privilegio", "publicar modelo para toda a plataforma exige superadmin") from e


@router.get(
    "/api/modelos/{id}/pacote", openapi_extra=LER, responses={200: {"content": {"application/zip": {}}}}
)
def baixar_modelo(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        r = pacote.modelo_ou_404(cur, uuid_ok(id, "modelo_inexistente", "modelo inexistente"))
    return Response(
        bytes(r["conteudo"]),
        media_type="application/zip",
        headers={**ZIP, "Content-Disposition": f'attachment; filename="modelo-{r["id"]}.zip"'},
    )


@router.delete("/api/modelos/{id}", status_code=204, openapi_extra=IMPORTAR)
def apagar_modelo(id: str, request: Request, auth: Auth = autenticado("conteudo.criar", so_sessao=True)):
    mid = uuid_ok(id, "modelo_inexistente", "modelo inexistente")
    with db.db(auth.contexto()) as cur:
        r = pacote.modelo_ou_404(cur, mid)
        cur.execute("DELETE FROM plat.pacote_modelo WHERE id = %s::uuid", (mid,))
        if cur.rowcount == 0:  # a política de linha recusou em silêncio (modelo de outro inquilino/escopo)
            raise ErroAPI(403, "sem_privilegio", "este modelo não é do seu inquilino")
        registrar_evento(cur, request, "modelos/apagar", "modelo", mid, {"nome": r["nome"][:200]})
    return Response(status_code=204)
