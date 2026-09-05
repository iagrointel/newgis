"""Console mínimo do superadmin (ADR 0002 seção 10): inquilinos. 404 para quem não é superadmin (a rota não se
confirma); o superadmin é resolvido pelo hash da sessão dentro das funções plataforma_*/tenant_* (nunca por GUC)."""

import re
import secrets

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db, limites, senha
from app.auth.comum import erro_do_banco, registrar_evento
from app.auth.modelos import Inquilino, InquilinoCriado, InquilinoCriar
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI

router = APIRouter(prefix="/api/plataforma", tags=["plataforma"])
SUPER = {"x-auth": "S", "x-privilegio": "superadmin"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")


@router.get("/inquilinos", response_model=list[Inquilino], openapi_extra=SUPER)
def listar(auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.tenant_listar(%s)", (auth.sessao_hash,))
            return [
                {**r, "criado_em": iso(r["criado_em"]), "ultimo_acesso": iso(r["ultimo_acesso"])}
                for r in cur.fetchall()
            ]
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.post("/inquilinos", response_model=InquilinoCriado, status_code=201, openapi_extra=SUPER)
def criar(corpo: InquilinoCriar, request: Request, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    slug = corpo.slug.strip().lower()
    if not SLUG.match(slug):
        raise ErroAPI(422, "validacao", "slug: minúsculas, dígitos e hífen, 2 a 39 caracteres", {"campo": "slug"})
    temporaria = secrets.token_urlsafe(limites.SENHA_TEMPORARIA_TAMANHO)[: limites.SENHA_TEMPORARIA_TAMANHO]
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT * FROM plat.tenant_criar(%s, %s, %s, %s::jsonb, %s, %s, %s)",
                (
                    auth.sessao_hash,
                    slug,
                    corpo.nome.strip(),
                    __import__("json").dumps(corpo.config or {}),
                    corpo.admin_login.strip().lower(),
                    corpo.admin_nome.strip(),
                    senha.gerar_hash(temporaria),
                ),
            )
            r = cur.fetchone()
        with db.db(auth.contexto()) as cur:
            registrar_evento(cur, request, "inquilinos/criar", "inquilino", r["tenant_id"], {"slug": slug})
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "slug_existente", "já existe um inquilino com esse identificador") from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {
        "id": r["tenant_id"],
        "slug": slug,
        "admin": {"id": r["usuario_id"], "login": corpo.admin_login.strip().lower()},
        "senha_temporaria": temporaria,
    }


def _suspender(auth: Auth, request: Request, id: int, ativo: bool) -> Response:
    try:
        with db.db() as cur:
            cur.execute("SELECT plat.tenant_suspender(%s, %s, %s)", (auth.sessao_hash, id, ativo))
        with db.db(auth.contexto()) as cur:
            registrar_evento(cur, request, "inquilinos/reativar" if ativo else "inquilinos/suspender", "inquilino", id)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


@router.post("/inquilinos/{id}/suspender", status_code=204, response_class=Response, openapi_extra=SUPER)
def suspender(id: int, request: Request, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    return _suspender(auth, request, id, False)


@router.delete("/inquilinos/{id}", status_code=204, response_class=Response, openapi_extra=SUPER)
def apagar(id: int, request: Request, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    """Apaga o inquilino inteiro (usuários, sessões, tokens, grupos, papéis, log, eventos, jobs) pela função
    plat.tenant_apagar; `plataforma` não se apaga (409). Sem lixeira: é operação do superadmin, com evento."""
    try:
        with db.db() as cur:
            cur.execute("SELECT slug FROM plat.tenant_listar(%s) WHERE id = %s", (auth.sessao_hash, id))
            r = cur.fetchone()
            if r is None:
                raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
            cur.execute("SELECT plat.tenant_apagar(%s, %s)", (auth.sessao_hash, id))
        with db.db(auth.contexto()) as cur:
            registrar_evento(cur, request, "inquilinos/apagar", "inquilino", id, {"slug": r["slug"]})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


@router.post("/inquilinos/{id}/reativar", status_code=204, response_class=Response, openapi_extra=SUPER)
def reativar(id: int, request: Request, auth: Auth = autenticado(superadmin=True, so_sessao=True)):
    return _suspender(auth, request, id, True)
