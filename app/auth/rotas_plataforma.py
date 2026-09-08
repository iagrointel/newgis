"""Console do superadmin (ADR 0002 seção 10; item L0-07-f-console-plataforma): um portal com N inquilinos, fora de
qualquer inquilino. 404 para quem não é superadmin (a rota não se confirma); o superadmin é resolvido pelo hash da
sessão dentro das funções plataforma_*/tenant_* (nunca por GUC, nunca por cookie forjado: o hash tem de existir em
plat.sessao ligado a um usuário superadmin do inquilino `plataforma`).

Rotas: listar com uso · criar (slug, nome, admin com senha temporária, cotas, config inicial) · detalhe (cotas, uso,
administradores) · alterar cotas · suspender (com mensagem para os membros; 503 em toda credencial do inquilino,
dado intacto) · reativar · desligar o 2FA de um administrador do inquilino · apagar · fila agregada · eventos da
plataforma. Toda escrita registra evento no inquilino `plataforma` (trilha); não existe "entrar como" membro."""

import json
import re
import secrets
from typing import Any

import psycopg2
from fastapi import APIRouter, Body, Request, Response
from pydantic import Field

from app import db, limites, senha
from app.auth.comum import erro_do_banco, paginacao, registrar_evento
from app.auth.modelos import CotasEntrada, Inquilino, InquilinoCriado, InquilinoCriar, Modelo, Saida

from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI

router = APIRouter(prefix="/api/plataforma", tags=["plataforma"])
SUPER = {"x-auth": "S", "x-privilegio": "superadmin"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")
CHAVES_COTAS = ("cota_usuarios", "cota_jobs_dia", "cota_jobs_simultaneos", "cota_agendas", "cota_itens")
OPERADOR = autenticado(superadmin=True, so_sessao=True)


# ---------------------------------------------------------------- modelos
class SuspenderEntrada(Modelo):
    mensagem: str | None = Field(default=None, max_length=limites.PLATAFORMA_SUSPENSAO_MENSAGEM_MAX)


class InquilinoUso(Inquilino):
    usuarios_ativos: int
    cota_usuarios: int
    cota_bytes: int
    bytes_usados: int
    itens: int
    cota_itens: int
    jobs_pendentes: int
    jobs_rodando: int
    suspensao: dict[str, Any] | None


class InquilinoDetalhe(Saida):
    id: int
    slug: str
    nome: str
    ativo: bool
    criado_em: str | None
    ultimo_acesso: str | None
    suspensao: dict[str, Any] | None
    cotas: dict[str, int]
    uso: dict[str, int]
    admins: list[dict[str, Any]]


class FilaResumo(Saida):
    total: dict[str, int]
    mais_antigo_pendente_em: str | None
    por_inquilino: list[dict[str, Any]]
    workers: list[dict[str, Any]]


class PaginaEventos(Saida):
    total: int
    itens: list[dict[str, Any]]


# ---------------------------------------------------------------- apoio
def _linha(r: dict) -> dict:
    return {**r, "criado_em": iso(r["criado_em"]), "ultimo_acesso": iso(r["ultimo_acesso"])}


def _cotas_jsonb(cotas: CotasEntrada | None) -> str:
    if cotas is None:
        return "{}"
    return json.dumps({k: v for k, v in cotas.model_dump().items() if k in CHAVES_COTAS and v is not None})


def _evento(auth: Auth, request: Request, tipo: str, alvo_id: int, propriedades: dict | None = None) -> None:
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, tipo, "inquilino", alvo_id, propriedades)


def _detalhe(auth: Auth, id: int) -> dict:
    with db.db() as cur:
        cur.execute("SELECT plat.tenant_detalhe(%s, %s) AS d", (auth.sessao_hash, id))
        return cur.fetchone()["d"]


# ---------------------------------------------------------------- inquilinos
@router.get("/inquilinos", response_model=list[InquilinoUso], openapi_extra=SUPER)
def listar(auth: Auth = OPERADOR):
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.tenant_listar_uso(%s)", (auth.sessao_hash,))
            return [_linha(r) for r in cur.fetchall()]
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.post("/inquilinos", response_model=InquilinoCriado, status_code=201, openapi_extra=SUPER)
def criar(corpo: InquilinoCriar, request: Request, auth: Auth = OPERADOR):
    slug = corpo.slug.strip().lower()
    if not SLUG.match(slug):
        raise ErroAPI(422, "validacao", "slug: minúsculas, dígitos e hífen, 2 a 39 caracteres", {"campo": "slug"})
    temporaria = secrets.token_urlsafe(limites.SENHA_TEMPORARIA_TAMANHO)[: limites.SENHA_TEMPORARIA_TAMANHO]
    cotas = corpo.cotas
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT * FROM plat.tenant_criar(%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)",
                (
                    auth.sessao_hash,
                    slug,
                    corpo.nome.strip(),
                    json.dumps(corpo.config or {}),
                    corpo.admin_login.strip().lower(),
                    corpo.admin_nome.strip(),
                    senha.gerar_hash(temporaria),
                    cotas.cota_bytes if cotas else None,
                    _cotas_jsonb(cotas),
                ),
            )
            r = cur.fetchone()
        _evento(auth, request, "inquilinos/criar", r["tenant_id"], {"slug": slug, "cotas": json.loads(_cotas_jsonb(cotas))})
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "slug_existente", "já existe um inquilino com esse identificador") from e
    except psycopg2.errors.CheckViolation as e:
        # defesa em profundidade: o CHECK de plat.tenant.slug é a mesma expressão de SLUG acima
        raise ErroAPI(422, "validacao", "slug recusado pela restrição do banco", {"campo": "slug"}) from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {
        "id": r["tenant_id"],
        "slug": slug,
        "admin": {"id": r["usuario_id"], "login": corpo.admin_login.strip().lower()},
        "senha_temporaria": temporaria,
    }


@router.get("/inquilinos/{id}", response_model=InquilinoDetalhe, openapi_extra=SUPER)
def detalhe(id: int, auth: Auth = OPERADOR):
    try:
        d = _detalhe(auth, id)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return d


@router.put("/inquilinos/{id}/cotas", response_model=InquilinoDetalhe, openapi_extra=SUPER)
def alterar_cotas(id: int, corpo: CotasEntrada, request: Request, auth: Auth = OPERADOR):
    if all(v is None for v in corpo.model_dump().values()):
        raise ErroAPI(422, "validacao", "informe ao menos uma cota")
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT plat.tenant_cotas_alterar(%s, %s, %s, %s::jsonb)",
                (auth.sessao_hash, id, corpo.cota_bytes, _cotas_jsonb(corpo)),
            )
        _evento(auth, request, "inquilinos/cotas", id, {k: v for k, v in corpo.model_dump().items() if v is not None})
        d = _detalhe(auth, id)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return d


def _suspender(auth: Auth, request: Request, id: int, ativo: bool, mensagem: str | None = None) -> Response:
    try:
        with db.db() as cur:
            cur.execute("SELECT plat.tenant_suspender(%s, %s, %s, %s)", (auth.sessao_hash, id, ativo, mensagem))
        _evento(
            auth,
            request,
            "inquilinos/reativar" if ativo else "inquilinos/suspender",
            id,
            None if ativo else {"mensagem": mensagem},
        )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


@router.post("/inquilinos/{id}/suspender", status_code=204, response_class=Response, openapi_extra=SUPER)
def suspender(
    id: int,
    request: Request,
    corpo: SuspenderEntrada | None = Body(default=None),
    auth: Auth = OPERADOR,
):
    """Suspende: login, sessão viva e token do inquilino passam a receber 503 `inquilino_suspenso` com a
    mensagem (quando dada); nada é apagado. O inquilino `plataforma` não se suspende (409)."""
    mensagem = (corpo.mensagem or "").strip() if corpo else ""
    return _suspender(auth, request, id, False, mensagem or None)


@router.post("/inquilinos/{id}/reativar", status_code=204, response_class=Response, openapi_extra=SUPER)
def reativar(id: int, request: Request, auth: Auth = OPERADOR):
    return _suspender(auth, request, id, True)


@router.post(
    "/inquilinos/{id}/admins/{usuario_id}/2fa/desativar",
    status_code=204,
    response_class=Response,
    openapi_extra=SUPER,
)
def desligar_2fa_de_admin(id: int, usuario_id: int, request: Request, auth: Auth = OPERADOR):
    """Desliga o segundo fator de um ADMINISTRADOR do inquilino (o que a Esri resolve por chamado ao suporte):
    só perfil admin (409 para membro comum: o admin do inquilino faz isso), nunca no inquilino `plataforma`
    (409), sessões do alvo encerradas, evento com o login do alvo."""
    try:
        with db.db() as cur:
            cur.execute("SELECT plat.tenant_admin_2fa_desligar(%s, %s, %s) AS login", (auth.sessao_hash, id, usuario_id))
            login = cur.fetchone()["login"]
        _evento(auth, request, "inquilinos/2fa_desligar", id, {"usuario_id": usuario_id, "login": login})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


@router.delete("/inquilinos/{id}", status_code=204, response_class=Response, openapi_extra=SUPER)
def apagar(id: int, request: Request, auth: Auth = OPERADOR):
    """Apaga o inquilino inteiro (usuários, sessões, tokens, grupos, papéis, log, eventos, jobs) pela função
    plat.tenant_apagar; `plataforma` não se apaga (409). Sem lixeira: é operação do superadmin, com evento."""
    try:
        with db.db() as cur:
            cur.execute("SELECT slug FROM plat.tenant_listar(%s) WHERE id = %s", (auth.sessao_hash, id))
            r = cur.fetchone()
            if r is None:
                raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
            cur.execute("SELECT plat.tenant_apagar(%s, %s)", (auth.sessao_hash, id))
        _evento(auth, request, "inquilinos/apagar", id, {"slug": r["slug"]})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


# ---------------------------------------------------------------- fila e eventos da plataforma
@router.get("/fila", response_model=FilaResumo, openapi_extra=SUPER)
def fila(auth: Auth = OPERADOR):
    """Fila de jobs agregada: totais, por inquilino, o pendente mais antigo já vencido e os workers vivos."""
    try:
        with db.db() as cur:
            cur.execute("SELECT plat.plataforma_fila_resumo(%s) AS r", (auth.sessao_hash,))
            return cur.fetchone()["r"]
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.get("/eventos", response_model=PaginaEventos, openapi_extra=SUPER)
def eventos(
    tipo: str | None = None,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = OPERADOR,
):
    """Trilha do próprio console (eventos do inquilino `plataforma`: criar, suspender, cotas, 2fa, leituras de
    outro inquilino...). Eventos de OUTRO inquilino continuam só por GET /api/eventos + X-Plat-Inquilino, que
    registra a leitura."""
    lim, desl = paginacao(limite, deslocamento, limites.LOG_LIMITE_MAX)
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.plataforma_eventos(%s, %s, %s, %s)", (auth.sessao_hash, tipo, lim, desl))
            linhas = cur.fetchall()
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    itens = [
        {
            "id": r["id"],
            "em": iso(r["em"]),
            "tipo": r["tipo"],
            "ator": ({"id": r["ator_id"], "login": r["ator_login"]} if r["ator_id"] else None),
            "alvo_tipo": r["alvo_tipo"],
            "alvo_id": r["alvo_id"],
            "propriedades": r["propriedades"],
            "ip": r["ip"],
            "req_id": r["req_id"],
        }
        for r in linhas
    ]
    return {"total": linhas[0]["total"] if linhas else 0, "itens": itens}
