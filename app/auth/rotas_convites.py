"""Convite de membro por e-mail (item L0-07-d-smtp-convites; ADR 0013): `POST/GET/DELETE /api/convites` sob
sessão (mesmos privilégios de `POST /api/usuarios`: `membros.gerir` sempre, `membros.papel` quando o convite
pede perfil diferente de visualizador ou um papel — o convite cria a conta que `criar_usuario` criaria na
hora, só que mais tarde e com senha escolhida pelo convidado, então carrega o MESMO teto) e as duas rotas
públicas que resolvem/aceitam o token sem sessão nenhuma: `GET /api/convites/resolver` e
`POST /api/convites/aceitar`. O link nunca carrega o e-mail nem o perfil — só o token; o servidor sempre lê o
que o CONVITE guarda (nunca o que a URL ou o corpo alegam), o que fecha a refutação "altera o e-mail no link"
por construção (não há e-mail no link para alterar)."""

import secrets

import psycopg2
import psycopg2.errors
from fastapi import APIRouter, Request, Response

from app import db, limites
from app.auth import privilegios as priv
from app.auth.comum import erro_do_banco, paginacao, registrar_evento
from app.auth.modelos_convite import (
    Convite,
    ConviteAceitarEntrada,
    ConviteAceito,
    ConviteEntrada,
    ConviteResolvido,
)
from app.auth.politica import email_permitido
from app.auth.sessao import Auth, autenticado, iso, sha256_hex
from app.correio import textos
from app.correio.config import smtp_efetivo
from app.erros import ErroAPI
from app.jobs import sistema as jobs_sistema
from app.settings import settings

router = APIRouter(prefix="/api/convites", tags=["convites"])
PRIV = {"x-auth": "S/T", "x-privilegio": "membros.gerir"}
SQL_CONVITE = """
SELECT c.id, c.email, c.nome_sugerido, c.perfil, c.papel_id, p.nome AS papel_nome, c.criado_em, c.expira_em,
       c.usado_em, c.cancelado_em, c.criado_por, u.login AS criado_por_login
FROM plat.convite c LEFT JOIN plat.papel_personalizado p ON p.id = c.papel_id
                    LEFT JOIN plat.usuario u ON u.id = c.criado_por
"""


def _json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "email": r["email"],
        "nome_sugerido": r["nome_sugerido"],
        "perfil": r["perfil"],
        "papel": ({"id": r["papel_id"], "nome": r["papel_nome"]} if r.get("papel_id") else None),
        "criado_por": ({"id": r["criado_por"], "login": r["criado_por_login"]} if r.get("criado_por") else None),
        "criado_em": iso(r["criado_em"]),
        "expira_em": iso(r["expira_em"]),
        "usado_em": iso(r["usado_em"]),
        "cancelado_em": iso(r["cancelado_em"]),
    }


def _link(token: str) -> str:
    return f"{settings.PLAT_URL_PUBLICA}/aceitar-convite?token={token}"


@router.get("", response_model=list[Convite], openapi_extra=PRIV)
def listar(limite: int | None = None, deslocamento: int | None = None, auth: Auth = autenticado("membros.gerir")):
    lim, desl = paginacao(limite, deslocamento, maximo=limites.CONVITE_LISTA_MAX)
    with db.db(auth.contexto()) as cur:
        cur.execute(SQL_CONVITE + " WHERE c.cancelado_em IS NULL AND c.usado_em IS NULL "
                    "ORDER BY c.criado_em DESC LIMIT %s OFFSET %s", (lim, desl))
        return [_json(r) for r in cur.fetchall()]


@router.post("", response_model=Convite, status_code=201, openapi_extra=PRIV)
def convidar(corpo: ConviteEntrada, request: Request, auth: Auth = autenticado("membros.gerir")):
    if corpo.perfil == "admin" and auth.perfil != "admin":
        raise ErroAPI(403, "so_admin_convida_admin", "só um administrador convida outro administrador")
    if (corpo.perfil != "visualizador" or corpo.papel_id is not None) and not auth.tem("membros.papel"):
        raise ErroAPI(403, "sem_privilegio",
                      "convidar com perfil diferente de visualizador, ou com papel, exige membros.papel",
                      {"exigido": "membros.papel"})
    if not email_permitido(corpo.email, auth.politica):
        raise ErroAPI(422, "email_dominio", "e-mail fora dos domínios permitidos do inquilino",
                      {"dominios": list(auth.politica.dominios_email)})
    token = "conv_" + secrets.token_urlsafe(32)
    try:
        with db.db(auth.contexto()) as cur:
            if corpo.papel_id is not None:
                cur.execute("SELECT perfil_minimo FROM plat.papel_personalizado WHERE id = %s", (corpo.papel_id,))
                p = cur.fetchone()
                if p is None:
                    raise ErroAPI(404, "papel_inexistente", "papel inexistente")
                if priv.ORDEM_PERFIL[corpo.perfil] < priv.ORDEM_PERFIL[p["perfil_minimo"]]:
                    raise ErroAPI(422, "papel_incompativel", f"o papel exige perfil {p['perfil_minimo']} ou maior",
                                  {"perfil_minimo": p["perfil_minimo"]})
            # reenviar substitui o convite pendente do mesmo e-mail (nunca acumula tokens vivos para o mesmo destino)
            cur.execute(
                "UPDATE plat.convite SET cancelado_em = now() WHERE tenant_id = %s AND lower(email) = lower(%s) "
                "AND usado_em IS NULL AND cancelado_em IS NULL",
                (auth.tenant_id, corpo.email),
            )
            cur.execute(
                "INSERT INTO plat.convite(tenant_id, email, nome_sugerido, perfil, papel_id, token_hash, "
                "criado_por, expira_em) VALUES (%s, %s, %s, %s, %s, %s, %s, now() + %s * interval '1 day') "
                "RETURNING id",
                (auth.tenant_id, corpo.email.strip(), corpo.nome_sugerido, corpo.perfil, corpo.papel_id,
                 sha256_hex(token), auth.usuario_id, limites.CONVITE_VALIDADE_DIAS),
            )
            novo = cur.fetchone()["id"]
            cur.execute("SELECT config FROM plat.tenant WHERE id = plat.tenant_atual()")
            config = cur.fetchone()["config"]
            registrar_evento(cur, request, "convites/criar", "convite", novo,
                             {"email": corpo.email.strip(), "perfil": corpo.perfil})
            cur.execute(SQL_CONVITE + " WHERE c.id = %s", (novo,))
            saida = _json(cur.fetchone())
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    if smtp_efetivo(config, settings) is not None:
        jobs_sistema.enfileirar(
            auth.tenant_id, "correio.enviar",
            {"destinatario": corpo.email.strip(), "assunto": textos.convite_assunto(auth.tenant_nome),
             "texto": textos.convite_texto(auth.tenant_nome, _link(token), limites.CONVITE_VALIDADE_DIAS),
             "categoria": "convite"},
            usuario_id=auth.usuario_id,
        )
    # sem SMTP: caminho manual — o admin repassa o link (mostrado uma única vez, como a senha temporária)
    saida["link_manual"] = None if smtp_efetivo(config, settings) is not None else _link(token)
    return saida


@router.delete("/{id}", status_code=204, response_class=Response, openapi_extra=PRIV)
def cancelar(id: str, request: Request, auth: Auth = autenticado("membros.gerir")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT id FROM plat.convite WHERE id = %s::uuid AND usado_em IS NULL AND cancelado_em IS NULL",
                    (id,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "convite_inexistente", "convite inexistente ou já resolvido")
        cur.execute("UPDATE plat.convite SET cancelado_em = now() WHERE id = %s::uuid", (id,))
        registrar_evento(cur, request, "convites/cancelar", "convite", id, {})
    return Response(status_code=204)


# ---------------------------------------------------------------- público (sem sessão)
@router.get("/resolver", response_model=ConviteResolvido, openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def resolver(token: str):
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.convite_resolver(%s)", (sha256_hex(token),))
        r = cur.fetchone()
    if r["motivo"] != "ok":
        raise ErroAPI(410, f"convite_{r['motivo']}", "este convite não pode mais ser usado", {"motivo": r["motivo"]})
    return {"motivo": "ok", "tenant_nome": r["tenant_nome"], "email": r["email"], "perfil": r["perfil"],
            "expira_em": iso(r["expira_em"])}


@router.post("/aceitar", response_model=ConviteAceito, openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def aceitar(corpo: ConviteAceitarEntrada, request: Request):
    from app import senha as senha_mod
    from app.auth.politica import mensagem_da_regra, politica_de, regra_da_senha

    with db.db() as cur:
        cur.execute("SELECT * FROM plat.convite_resolver(%s)", (sha256_hex(corpo.token),))
        info = cur.fetchone()
    if info["motivo"] != "ok":
        raise ErroAPI(410, f"convite_{info['motivo']}", "este convite não pode mais ser usado",
                      {"motivo": info["motivo"]})
    with db.db() as cur:
        cur.execute("SELECT config FROM plat.tenant WHERE slug = %s", (info["tenant_slug"],))
        config = cur.fetchone()["config"]
    politica = politica_de(config, info["tenant_slug"])
    regra = regra_da_senha(corpo.senha, politica, corpo.login, info["tenant_slug"], corpo.nome)
    if regra:
        raise ErroAPI(422, "senha_fraca", mensagem_da_regra(regra, politica), {"regra": regra})
    senha_hash = senha_mod.gerar_hash(corpo.senha)
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.convite_aceitar(%s, %s, %s, %s)",
                        (sha256_hex(corpo.token), corpo.login.strip().lower(), corpo.nome.strip(), senha_hash))
            r = cur.fetchone()
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "login_existente", "já existe um usuário com esse login neste inquilino") from e
    if r["motivo"] == "ok":
        with db.db(db.Contexto(r["tenant_id"], r["usuario_id"], r["login"])) as cur:
            registrar_evento(cur, request, "usuarios/convite_aceito", "usuario", r["usuario_id"],
                             {"convite_token_hash": sha256_hex(corpo.token)[:12]})
        return {"ok": True, "tenant_slug": info["tenant_slug"], "login": r["login"]}
    if r["motivo"] == "invalido":
        raise ErroAPI(410, "convite_invalido", "este convite não pode mais ser usado", {"motivo": "invalido"})
    raise ErroAPI(410, f"convite_{r['motivo']}", "este convite não pode mais ser usado", {"motivo": r["motivo"]})
