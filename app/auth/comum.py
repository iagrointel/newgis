"""Auxiliares das rotas de identidade: objeto `usuario` da seção 14 do ADR 0002, eventos de domínio, tradução
de exceção do banco (gatilhos e funções levantam códigos curtos) para ErroAPI, paginação, cookie de sessão."""

import json
from typing import Any

import psycopg2
import psycopg2.errors
from fastapi import Request, Response

from app import limites
from app.auth.sessao import COOKIE, Auth, ip_de, iso
from app.erros import ErroAPI
from app.settings import settings

SQL_USUARIO = """
SELECT u.id, u.login, u.nome, u.email, u.perfil, u.superadmin, u.ativo, u.origem, u.totp_ativo, u.trocar_senha,
       u.bloqueado_ate, u.ultimo_login, u.ultimo_ip, u.criado_em, u.papel_id, u.senha_alterada_em,
       cardinality(coalesce(u.codigos_recuperacao, '{}'::text[])) AS codigos_restantes,
       p.nome AS papel_nome
FROM plat.usuario u LEFT JOIN plat.papel_personalizado p ON p.id = u.papel_id
"""
CAMPOS_V = ("id", "login", "nome", "perfil", "papel", "ativo", "origem", "ultimo_login", "criado_em")
ERROS_DO_BANCO = {
    "ultimo_admin": (409, "é o último administrador ativo; nomeie outro antes"),
    "dono_nao_sai": (409, "o dono não sai do grupo; transfira o grupo antes"),
    "grupo_administrativo": (409, "grupo administrativo: o membro não sai"),
    "so_superadmin": (404, "recurso inexistente"),
    "slug_reservado": (409, "este identificador é reservado"),
    "inquilino_inexistente": (404, "inquilino inexistente"),
    "plataforma_nao_suspende": (409, "o inquilino da plataforma não se suspende"),
    "plataforma_nao_apaga": (409, "o inquilino da plataforma não se apaga"),
    "inquilino_com_dependencias": (409, "o inquilino ainda tem dados referenciados; tente de novo"),
    "usuario_de_outro_inquilino": (404, "usuário inexistente"),
    "dono_de_outro_inquilino": (422, "o dono precisa ser membro do inquilino"),
    "grupo_de_outro_inquilino": (404, "grupo inexistente"),
    "contexto_de_outro_inquilino": (403, "operação fora do inquilino da sessão"),
    "superadmin_so_plataforma": (422, "superadmin só no inquilino da plataforma"),
    "usuario_inativo_ou_inquilino_suspenso": (401, "usuário inativo ou inquilino suspenso"),
}


def usuario_json(r: dict, completo: bool = True) -> dict:
    u = {
        "id": r["id"],
        "login": r["login"],
        "nome": r["nome"],
        "perfil": r["perfil"],
        "papel": ({"id": r["papel_id"], "nome": r["papel_nome"]} if r.get("papel_id") else None),
        "ativo": r["ativo"],
        "origem": r["origem"],
        "ultimo_login": iso(r["ultimo_login"]),
        "criado_em": iso(r["criado_em"]),
    }
    if completo:
        u.update(
            {
                "email": r["email"],
                "superadmin": r["superadmin"],
                "totp_ativo": r["totp_ativo"],
                "trocar_senha": r["trocar_senha"],
                "bloqueado_ate": iso(r["bloqueado_ate"]),
                "ultimo_ip": r["ultimo_ip"],
                "codigos_recuperacao_restantes": r.get("codigos_restantes", 0),
            }
        )
    return u


def carregar_usuario(cur, usuario_id: int) -> dict | None:
    cur.execute(SQL_USUARIO + " WHERE u.id = %s", (usuario_id,))
    return cur.fetchone()


def usuario_ou_404(cur, usuario_id: int) -> dict:
    r = carregar_usuario(cur, usuario_id)
    if r is None:
        raise ErroAPI(404, "usuario_inexistente", "usuário inexistente")
    return r


def registrar_evento(
    cur,
    request: Request,
    tipo: str,
    alvo_tipo: str | None = None,
    alvo_id: Any = None,
    propriedades: dict | None = None,
) -> None:
    """Evento no contexto atual do cursor (a função exige contexto; nunca carrega segredo)."""
    cur.execute(
        "SELECT plat.evento_registrar(%s, %s, %s, %s::jsonb, %s, %s)",
        (
            tipo,
            alvo_tipo,
            None if alvo_id is None else str(alvo_id),
            json.dumps(propriedades or {}, default=str),
            ip_de(request),
            getattr(request.state, "req_id", None),
        ),
    )


def erro_do_banco(e: Exception) -> ErroAPI:
    """RaiseException com código curto → ErroAPI; violação de unicidade/CHECK/FK → 409/422."""
    if isinstance(e, psycopg2.errors.RaiseException):
        codigo = (e.diag.message_primary or "").strip()
        if codigo in ERROS_DO_BANCO:
            status, mensagem = ERROS_DO_BANCO[codigo]
            return ErroAPI(status, codigo, mensagem)
        return ErroAPI(409, "regra_do_banco", codigo or "regra do banco recusou a operação")
    if isinstance(e, psycopg2.errors.UniqueViolation):
        return ErroAPI(409, "conflito", "já existe um registro com esse valor", {"restricao": e.diag.constraint_name})
    if isinstance(e, psycopg2.errors.CheckViolation):
        return ErroAPI(422, "validacao", "valor fora do permitido", {"restricao": e.diag.constraint_name})
    if isinstance(e, psycopg2.errors.ForeignKeyViolation):
        return ErroAPI(409, "em_uso", "registro referenciado por outro", {"restricao": e.diag.constraint_name})
    if isinstance(e, psycopg2.errors.InsufficientPrivilege):
        return ErroAPI(403, "sem_permissao", "operação fora do inquilino da sessão")
    if isinstance(e, psycopg2.errors.ReadOnlySqlTransaction):
        return ErroAPI(403, "somente_leitura", "leitura de outro inquilino não permite escrita")
    raise e


def paginacao(limite: int | None, deslocamento: int | None, maximo: int = limites.PAGINA_MAX) -> tuple[int, int]:
    lim = limites.PAGINA_PADRAO if limite is None else limite
    if lim < 1 or lim > maximo:
        raise ErroAPI(422, "validacao", f"limite entre 1 e {maximo}", {"campo": "limite"})
    desl = deslocamento or 0
    if desl < 0:
        raise ErroAPI(422, "validacao", "deslocamento não pode ser negativo", {"campo": "deslocamento"})
    return lim, desl


def cookie_seguro(request: Request) -> bool:
    if settings.producao:
        return True
    return (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"


def emitir_cookie(resposta: Response, request: Request, valor: str, max_dias: int) -> None:
    resposta.set_cookie(
        COOKIE, valor, max_age=max_dias * 86400, path="/", httponly=True, secure=cookie_seguro(request), samesite="lax"
    )


def apagar_cookie(resposta: Response, request: Request) -> None:
    resposta.set_cookie(
        COOKIE, "", max_age=0, expires=0, path="/", httponly=True, secure=cookie_seguro(request), samesite="lax"
    )


def so_admin_sobre_admin(auth: Auth, alvo_perfil: str, novo_perfil: str | None, codigo: str) -> None:
    """Regras (b)(c) da seção 2.3: mexer em admin (ou promover a admin) exige ser admin."""
    if (alvo_perfil == "admin" or novo_perfil == "admin") and auth.perfil != "admin":
        raise ErroAPI(403, codigo, "só um administrador altera outro administrador")


def campos_json(corpo: Any, permitidos: set[str]) -> dict:
    if not isinstance(corpo, dict):
        raise ErroAPI(422, "validacao", "o corpo precisa ser um objeto JSON")
    extras = sorted(set(corpo) - permitidos)
    if extras:
        raise ErroAPI(400, "campo_nao_editavel", f"campo não editável: {', '.join(extras)}", extras)
    return corpo


CONFIG_PUBLICA = ("centro", "zoom", "basemap", "srid_padrao", "cor", "logo")


def eu_json(cur, auth: Auth) -> dict:
    """Objeto de /api/eu (ADR 0002 seção 14): usuário completo + privilégios + inquilino + pendências + sessão/token."""
    r = usuario_ou_404(cur, auth.usuario_id)
    u = usuario_json(r, completo=True)
    u["privilegios"] = list(auth.privilegios)
    config_publica = {k: v for k, v in (auth.config or {}).items() if k in CONFIG_PUBLICA}
    config_publica["auth"] = auth.politica.publica()
    u["inquilino"] = {"slug": auth.tenant_slug, "nome": auth.tenant_nome, "config_publica": config_publica}
    u["pendencias"] = list(auth.pendencias)
    if auth.modo == "sessao":
        u["sessao"] = auth.sessao
    else:
        u["token"] = auth.token
    return u
