"""/api/eu: a própria conta (dados, senha, sessões, 2FA, convites). Tudo sob sessão, exceto GET /api/eu (S/T).
ADR 0002 seções 5.1, 6.3, 7.3, 14."""

import psycopg2
from fastapi import APIRouter, Body, Request, Response

from app import db, limites, senha
from app.auth import totp
from app.auth.comum import campos_json, erro_do_banco, eu_json, registrar_evento
from app.auth.modelos import (
    CodigoEntrada,
    CodigosRecuperacao,
    Convite,
    Eu,
    Iniciar2FA,
    SenhaCodigoEntrada,
    SenhaEntrada,
    SenhaSoEntrada,
    Sessao,
)
from app.auth.politica import email_permitido, mensagem_da_regra, regra_da_senha
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/api/eu", tags=["eu"])
S = {"x-auth": "S", "x-privilegio": "proprio"}


def _so_local(auth: Auth) -> None:
    if auth.origem != "local":
        raise ErroAPI(409, "login_externo", "esta conta entra pelo login da organização; senha e 2FA são do provedor")


def _senha_confere(cur, auth: Auth, informada: str, codigo_erro: str = "senha_atual_incorreta") -> str:
    cur.execute("SELECT senha_hash FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
    atual = cur.fetchone()["senha_hash"]
    if not senha.verificar(informada, atual or ""):
        raise ErroAPI(401, codigo_erro, "senha atual incorreta")
    return atual


@router.get(
    "", response_model=Eu, response_model_exclude_unset=True, openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"}
)
def eu(auth: Auth = autenticado(escopo_token=None, permitir_pendencia=True)):
    with db.db(auth.contexto()) as cur:
        return eu_json(cur, auth)


@router.put("", response_model=Eu, response_model_exclude_unset=True, openapi_extra=S)
def editar_eu(request: Request, corpo: dict = Body(...), auth: Auth = autenticado(so_sessao=True)):
    campos = campos_json(corpo, {"nome", "email"})
    if "email" in campos and campos["email"] is not None and not email_permitido(campos["email"], auth.politica):
        raise ErroAPI(
            422,
            "email_dominio",
            "e-mail fora dos domínios permitidos do inquilino",
            {"dominios": list(auth.politica.dominios_email)},
        )
    nome = (campos.get("nome") or auth.nome).strip()
    if not nome:
        raise ErroAPI(422, "validacao", "nome não pode ser vazio", {"campo": "nome"})
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.usuario SET nome = %s, email = CASE WHEN %s THEN %s ELSE email END WHERE id = %s",
            (nome[:200], "email" in campos, campos.get("email"), auth.usuario_id),
        )
        registrar_evento(
            cur, request, "usuarios/atualizar", "usuario", auth.usuario_id, {"campos": sorted(campos), "proprio": True}
        )
        auth.nome = nome
        return eu_json(cur, auth)


@router.put("/senha", status_code=204, response_class=Response, openapi_extra=S)
def trocar_senha(
    corpo: SenhaEntrada, request: Request, auth: Auth = autenticado(so_sessao=True, permitir_pendencia=True)
):
    _so_local(auth)
    regra = regra_da_senha(corpo.nova, auth.politica, auth.login, auth.tenant_slug, auth.nome)
    if regra:
        raise ErroAPI(422, "senha_fraca", mensagem_da_regra(regra, auth.politica), {"regra": regra})
    try:
        with db.db(auth.contexto()) as cur:
            atual = _senha_confere(cur, auth, corpo.atual)
            n = auth.politica.senha_historico
            cur.execute(
                "SELECT senha_hash FROM plat.senha_historico WHERE usuario_id = %s ORDER BY criado_em DESC LIMIT %s",
                (auth.usuario_id, max(n - 1, 0)),
            )
            anteriores = [atual] + [r["senha_hash"] for r in cur.fetchall()] if n > 0 else []
            if any(senha.verificar(corpo.nova, h) for h in anteriores):
                raise ErroAPI(422, "senha_fraca", mensagem_da_regra("historico", auth.politica), {"regra": "historico"})
            cur.execute(
                "UPDATE plat.usuario SET senha_hash = %s, senha_alterada_em = now(), trocar_senha = false "
                "WHERE id = %s",
                (senha.gerar_hash(corpo.nova), auth.usuario_id),
            )
            if n > 0:
                cur.execute(
                    "INSERT INTO plat.senha_historico(usuario_id, senha_hash) VALUES (%s, %s)", (auth.usuario_id, atual)
                )
                cur.execute(
                    "DELETE FROM plat.senha_historico WHERE usuario_id = %s AND id NOT IN "
                    "(SELECT id FROM plat.senha_historico WHERE usuario_id = %s ORDER BY criado_em DESC LIMIT %s)",
                    (auth.usuario_id, auth.usuario_id, n),
                )
            cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, %s)", (auth.usuario_id, auth.sessao_hash))
            registrar_evento(cur, request, "usuarios/trocar_senha", "usuario", auth.usuario_id)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


@router.get("/sessoes", response_model=list[Sessao], openapi_extra=S)
def sessoes(auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT token_hash, criado_em, ultimo_uso, expira_em, ip, agente FROM plat.sessao "
            "WHERE usuario_id = %s ORDER BY criado_em DESC",
            (auth.usuario_id,),
        )
        return [
            {
                "id": r["token_hash"][:12],
                "criado_em": iso(r["criado_em"]),
                "ultimo_uso": iso(r["ultimo_uso"]),
                "expira_em": iso(r["expira_em"]),
                "ip": r["ip"],
                "agente": r["agente"],
                "atual": r["token_hash"] == auth.sessao_hash,
            }
            for r in cur.fetchall()
        ]


@router.delete("/sessoes", status_code=204, response_class=Response, openapi_extra=S)
def encerrar_outras(request: Request, outras: int = 0, auth: Auth = autenticado(so_sessao=True)):
    if outras != 1:
        raise ErroAPI(400, "pedido_invalido", "use ?outras=1 para encerrar as outras sessões")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, %s) AS n", (auth.usuario_id, auth.sessao_hash))
        n = cur.fetchone()["n"]
        registrar_evento(cur, request, "sessoes/revogar", "usuario", auth.usuario_id, {"outras": n})
    return Response(status_code=204)


@router.delete("/sessoes/{id}", status_code=204, response_class=Response, openapi_extra=S)
def encerrar_sessao(id: str, request: Request, auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "DELETE FROM plat.sessao WHERE usuario_id = %s AND left(token_hash, 12) = %s RETURNING token_hash",
            (auth.usuario_id, id[:12]),
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "sessao_inexistente", "sessão inexistente")
        registrar_evento(cur, request, "sessoes/revogar", "sessao", id[:12])
    return Response(status_code=204)


@router.post("/2fa/iniciar", response_model=Iniciar2FA, openapi_extra=S)
def iniciar_2fa(auth: Auth = autenticado(so_sessao=True, permitir_pendencia=True)):
    _so_local(auth)
    if auth.totp_ativo:
        raise ErroAPI(409, "ja_ativo", "o segundo fator já está ligado")
    segredo = totp.gerar_segredo()
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.usuario SET totp_secret = %s, totp_ativo = false, totp_ultimo_passo = NULL WHERE id = %s",
            (totp.cifrar(segredo, settings.PLAT_SECRET), auth.usuario_id),
        )
    uri = totp.uri(segredo, auth.tenant_slug, auth.login)
    return {"segredo": segredo, "uri": uri, "qr_svg": totp.qr_svg(uri)}


@router.post("/2fa/confirmar", response_model=CodigosRecuperacao, openapi_extra=S)
def confirmar_2fa(
    corpo: CodigoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True, permitir_pendencia=True)
):
    _so_local(auth)
    if auth.totp_ativo:
        raise ErroAPI(409, "ja_ativo", "o segundo fator já está ligado")
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT totp_secret, totp_ultimo_passo FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
        r = cur.fetchone()
        if not r["totp_secret"]:
            raise ErroAPI(409, "nao_iniciado", "chame /api/eu/2fa/iniciar antes")
        passo = totp.verificar(
            totp.decifrar(r["totp_secret"], settings.PLAT_SECRET), corpo.codigo, r["totp_ultimo_passo"]
        )
        if passo is None:
            raise ErroAPI(401, "codigo_invalido", "código inválido")
        codigos = totp.codigos_recuperacao()
        cur.execute(
            "UPDATE plat.usuario SET totp_ativo = true, totp_ultimo_passo = %s, codigos_recuperacao = %s WHERE id = %s",
            (passo, [totp.hash_recuperacao(c) for c in codigos], auth.usuario_id),
        )
        registrar_evento(cur, request, "usuarios/2fa_ligar", "usuario", auth.usuario_id)
    return {"codigos_recuperacao": codigos}


@router.post("/2fa/desativar", status_code=204, response_class=Response, openapi_extra=S)
def desativar_2fa(corpo: SenhaCodigoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    _so_local(auth)
    if auth.politica.exigir_2fa:
        raise ErroAPI(409, "2fa_obrigatorio", "o inquilino exige o segundo fator; ele não pode ser desligado")
    if not auth.totp_ativo:
        raise ErroAPI(409, "nao_ativo", "o segundo fator não está ligado")
    with db.db(auth.contexto()) as cur:
        _senha_confere(cur, auth, corpo.senha, "senha_incorreta")
        cur.execute("SELECT totp_secret, totp_ultimo_passo FROM plat.usuario WHERE id = %s", (auth.usuario_id,))
        r = cur.fetchone()
        if (
            totp.verificar(totp.decifrar(r["totp_secret"], settings.PLAT_SECRET), corpo.codigo, r["totp_ultimo_passo"])
            is None
        ):
            raise ErroAPI(401, "codigo_invalido", "código inválido")
        cur.execute(
            "UPDATE plat.usuario SET totp_secret = NULL, totp_ativo = false, totp_ultimo_passo = NULL, "
            "codigos_recuperacao = NULL WHERE id = %s",
            (auth.usuario_id,),
        )
        registrar_evento(cur, request, "usuarios/2fa_desligar", "usuario", auth.usuario_id, {"proprio": True})
    return Response(status_code=204)


@router.post("/2fa/codigos", response_model=CodigosRecuperacao, openapi_extra=S)
def novos_codigos(corpo: SenhaSoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    _so_local(auth)
    if not auth.totp_ativo:
        raise ErroAPI(409, "nao_ativo", "o segundo fator não está ligado")
    codigos = totp.codigos_recuperacao(limites.CODIGOS_RECUPERACAO)
    with db.db(auth.contexto()) as cur:
        _senha_confere(cur, auth, corpo.senha, "senha_incorreta")
        cur.execute(
            "UPDATE plat.usuario SET codigos_recuperacao = %s WHERE id = %s",
            ([totp.hash_recuperacao(c) for c in codigos], auth.usuario_id),
        )
        registrar_evento(cur, request, "usuarios/2fa_codigos", "usuario", auth.usuario_id)
    return {"codigos_recuperacao": codigos}


@router.get("/convites", response_model=list[Convite], openapi_extra=S)
def convites(auth: Auth = autenticado(so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            """
            SELECT g.id, g.nome, m.papel, m.criado_em, c.id AS c_id, c.nome AS c_nome, c.login AS c_login
            FROM plat.grupo_membro m JOIN plat.grupo g ON g.id = m.grupo_id
            LEFT JOIN plat.usuario c ON c.id = m.convidado_por
            WHERE m.usuario_id = %s AND m.estado = 'convidado' ORDER BY m.criado_em DESC""",
            (auth.usuario_id,),
        )
        return [
            {
                "grupo": {"id": str(r["id"]), "nome": r["nome"]},
                "papel": r["papel"],
                "convidado_por": ({"id": r["c_id"], "nome": r["c_nome"], "login": r["c_login"]} if r["c_id"] else None),
                "criado_em": iso(r["criado_em"]),
            }
            for r in cur.fetchall()
        ]
