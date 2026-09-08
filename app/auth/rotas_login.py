"""Login, segundo passo do 2FA e logout (ADR 0002 seções 5-7, 14). Ordem interna do login: auth_login (pré-contexto)
→ contexto do inquilino resolvido → suspenso? → origem? → bloqueado? → senha (ou HASH_FANTASMA, tempo constante)
→ auth_falha/auth_ok → 2FA? desafio : sessão + cookie → evento usuarios/entrar → resultado no log_acesso."""

import datetime

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db, senha
from app.auth import totp
from app.auth.comum import apagar_cookie, emitir_cookie, erro_do_banco, eu_json, registrar_evento
from app.auth.modelos import Login2FAEntrada, LoginEntrada, LoginSaida, Provedores
from app.auth.politica import HASH_FANTASMA, Politica, politica_de
from app.auth.sessao import (
    COOKIE,
    Auth,
    _auth_de_sessao,
    agente_de,
    ip_de,
    iso,
    ociosa_horas_padrao,
    resolver,
    sha256_hex,
)
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["login"])
MSG_CREDENCIAIS = "inquilino, usuário ou senha inválidos"


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _bloqueado(request: Request, ate) -> ErroAPI:
    request.state.resultado = "bloqueado"
    return ErroAPI(423, "bloqueado", f"usuário bloqueado até {iso(ate)}", {"bloqueado_ate": iso(ate)})


def _falhou(request: Request, ctx: db.Contexto, usuario_id: int, politica: Politica, resultado: str) -> None:
    """Conta a falha (senha, TOTP ou recuperação: o MESMO contador) e registra o evento quando bloqueia."""
    with db.db(ctx) as cur:
        cur.execute(
            "SELECT plat.auth_falha(%s, %s, %s, %s) AS ate",
            (usuario_id, politica.bloqueio_tentativas, politica.bloqueio_minutos, politica.bloqueio_janela_min),
        )
        ate = cur.fetchone()["ate"]
        if ate is not None and ate > _agora():
            registrar_evento(
                cur,
                request,
                "usuarios/falha_login",
                "usuario",
                usuario_id,
                {"bloqueado_ate": iso(ate), "fator": resultado},
            )
    request.state.resultado = resultado


# sentinela para "quem chama não trouxe a data de troca de senha; leia do banco". Existe porque o caminho do
# segundo fator (plat.auth_desafio_2fa_resolver) não devolve `senha_alterada_em`, e passar None ali significava
# "nunca expira" — quem ligava o 2FA ficava com a política de senha MAIS FRACA da plataforma (achado G1-b2 do
# adversário do turno 3). `None` continua sendo o valor legítimo de quem não tem senha local (LDAP).
NAO_INFORMADO = object()


def _abrir_sessao(
    request: Request,
    resposta: Response,
    ctx: db.Contexto,
    usuario_id: int,
    politica: Politica,
    fator: str,
    senha_alterada_em,
) -> dict:
    try:
        with db.db(ctx) as cur:
            cur.execute("SELECT plat.auth_ok(%s, %s)", (usuario_id, ip_de(request)))
            if senha_alterada_em is NAO_INFORMADO:
                cur.execute("SELECT senha_alterada_em FROM plat.usuario WHERE id = %s", (usuario_id,))
                linha_senha = cur.fetchone()
                senha_alterada_em = linha_senha["senha_alterada_em"] if linha_senha else None
            if (
                politica.senha_expira_dias
                and senha_alterada_em is not None
                and senha_alterada_em < _agora() - datetime.timedelta(days=politica.senha_expira_dias)
            ):
                cur.execute("UPDATE plat.usuario SET trocar_senha = true WHERE id = %s", (usuario_id,))
            cur.execute(
                "SELECT plat.auth_sessao_criar(%s, %s, %s, %s) AS tok",
                (usuario_id, politica.sessao_max_dias, ip_de(request), agente_de(request)),
            )
            tok = cur.fetchone()["tok"]
            registrar_evento(cur, request, "usuarios/entrar", "usuario", usuario_id, {"fator": fator})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    h = sha256_hex(tok)
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.auth_sessao(%s, %s)", (h, ociosa_horas_padrao()))
        r = cur.fetchone()
    auth: Auth = _auth_de_sessao(r, h)
    request.state.auth = auth
    request.state.resultado = "ok"
    with db.db(auth.contexto()) as cur:
        eu = eu_json(cur, auth)
    emitir_cookie(resposta, request, tok, politica.sessao_max_dias)
    return {"ok": True, "usuario": eu}


@router.get("/login/provedores", response_model=Provedores, openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def provedores(inquilino: str):
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.tenant_publico(%s)", (inquilino,))
        t = cur.fetchone()
    if t is None:
        raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
    # provedores externos nascem no L0-08; a lista vazia é o estado real, não um dado fixo
    return {"inquilino": {"slug": t["slug"], "nome": t["nome"]}, "provedores": [], "login_local": True}


@router.post(
    "/login",
    response_model=LoginSaida,
    response_model_exclude_unset=True,
    openapi_extra={"x-auth": "-", "x-privilegio": "publico"},
)
def login(corpo: LoginEntrada, request: Request, resposta: Response):
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.auth_login(%s, %s)", (corpo.inquilino.strip().lower(), corpo.login.strip()))
        r = cur.fetchone()
    if r is None:
        senha.verificar(corpo.senha, HASH_FANTASMA)  # mesmo custo do caminho real (tempo constante)
        request.state.resultado = "inexistente"
        raise ErroAPI(401, "credenciais_invalidas", MSG_CREDENCIAIS)
    request.state.tenant_id = r["tenant_id"]
    request.state.usuario_id = r["usuario_id"]
    if not r["ativo_tenant"]:
        senha.verificar(corpo.senha, HASH_FANTASMA)
        request.state.resultado = "suspenso"
        raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
    if r["origem"] != "local":
        request.state.resultado = "externo"
        raise ErroAPI(403, "login_externo", "esta conta entra pelo login da organização")
    politica = politica_de(r["config"], corpo.inquilino)
    if r["bloqueado_ate"] is not None and r["bloqueado_ate"] > _agora():
        senha.verificar(corpo.senha, HASH_FANTASMA)
        raise _bloqueado(request, r["bloqueado_ate"])
    ctx = db.Contexto(r["tenant_id"], r["usuario_id"], r["nome"] and corpo.login.strip().lower())
    certa = senha.verificar(corpo.senha, r["senha_hash"] or HASH_FANTASMA)
    if not certa or not r["ativo"]:
        if r["ativo"]:
            _falhou(request, ctx, r["usuario_id"], politica, "senha")
        else:
            request.state.resultado = "inativo"
        raise ErroAPI(401, "credenciais_invalidas", MSG_CREDENCIAIS)
    if r["totp_ativo"]:
        with db.db(ctx) as cur:
            cur.execute("SELECT plat.auth_desafio_2fa_criar(%s) AS d", (r["usuario_id"],))
            desafio = cur.fetchone()["d"]
            cur.execute(
                "SELECT cardinality(coalesce(codigos_recuperacao, '{}')) AS n FROM plat.usuario WHERE id = %s",
                (r["usuario_id"],),
            )
            restantes = cur.fetchone()["n"]
        request.state.resultado = "desafio"
        return {"ok": False, "exige_2fa": True, "desafio": desafio, "recuperacao_disponivel": restantes > 0}
    return _abrir_sessao(request, resposta, ctx, r["usuario_id"], politica, "senha", r["senha_alterada_em"])


@router.post(
    "/login/2fa",
    response_model=LoginSaida,
    response_model_exclude_unset=True,
    openapi_extra={"x-auth": "-", "x-privilegio": "publico"},
)
def login_2fa(corpo: Login2FAEntrada, request: Request, resposta: Response):
    if not corpo.codigo and not corpo.codigo_recuperacao:
        raise ErroAPI(422, "validacao", "informe codigo ou codigo_recuperacao")
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.auth_desafio_2fa_resolver(%s)", (sha256_hex(corpo.desafio),))
        r = cur.fetchone()
    if r is None or r["desafio_2fa_ate"] is None or r["desafio_2fa_ate"] < _agora():
        request.state.resultado = "desafio_expirado"
        raise ErroAPI(410, "desafio_expirado", "o desafio expirou; entre de novo com a senha")
    request.state.tenant_id = r["tenant_id"]
    request.state.usuario_id = r["usuario_id"]
    if not r["ativo_tenant"] or not r["ativo"]:
        request.state.resultado = "suspenso" if not r["ativo_tenant"] else "inativo"
        raise ErroAPI(401, "credenciais_invalidas", MSG_CREDENCIAIS)
    politica = politica_de(r["config"], "")
    if r["bloqueado_ate"] is not None and r["bloqueado_ate"] > _agora():
        raise _bloqueado(request, r["bloqueado_ate"])
    ctx = db.Contexto(r["tenant_id"], r["usuario_id"], r["login"])
    from app.settings import settings

    fator = None
    with db.db(ctx) as cur:
        if corpo.codigo:
            try:
                from app.seguranca_rotacao import decifrar_com_rotacao

                segredo = decifrar_com_rotacao(
                    totp.decifrar, r["totp_secret"] or "", settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR
                )
            except Exception:  # noqa: BLE001 — segredo ilegível (PLAT_SECRET e ANTERIOR trocados): só recuperação vale
                segredo = None
            passo = totp.verificar(segredo, corpo.codigo, r["totp_ultimo_passo"]) if segredo else None
            if passo is not None:
                cur.execute(
                    "UPDATE plat.usuario SET totp_ultimo_passo = %s, desafio_2fa_hash = NULL, "
                    "desafio_2fa_ate = NULL WHERE id = %s",
                    (passo, r["usuario_id"]),
                )
                fator = "totp"
            resultado = "totp"
        else:
            h = totp.hash_recuperacao(corpo.codigo_recuperacao)
            if h in (r["codigos_recuperacao"] or []):
                cur.execute(
                    "UPDATE plat.usuario SET codigos_recuperacao = array_remove(codigos_recuperacao, %s), "
                    "desafio_2fa_hash = NULL, desafio_2fa_ate = NULL WHERE id = %s",
                    (h, r["usuario_id"]),
                )
                fator = "recuperacao"
            resultado = "recuperacao"
    if fator is None:
        _falhou(request, ctx, r["usuario_id"], politica, resultado)
        raise ErroAPI(401, "codigo_invalido", "código inválido")
    # a política de senha do inquilino vale nos DOIS caminhos: o segundo fator é uma prova A MAIS, nunca uma
    # dispensa da expiração (achado G1-b2). A data vem do banco porque o desafio não a traz.
    return _abrir_sessao(request, resposta, ctx, r["usuario_id"], politica, fator, NAO_INFORMADO)


@router.post(
    "/logout", status_code=204, response_class=Response, openapi_extra={"x-auth": "S", "x-privilegio": "proprio"}
)
def logout(request: Request):
    cookie = request.cookies.get(COOKIE)
    if cookie:
        auth = None
        try:
            auth = resolver(request) if not request.headers.get("authorization") else None
        except ErroAPI:
            auth = None
        if auth is not None and auth.modo == "sessao":
            with db.db(auth.contexto()) as cur:
                registrar_evento(cur, request, "usuarios/sair", "usuario", auth.usuario_id)
                cur.execute("SELECT plat.auth_sessao_encerrar(%s)", (auth.sessao_hash,))
        else:
            with db.db() as cur:
                cur.execute("SELECT plat.auth_sessao_encerrar(%s)", (sha256_hex(cookie),))
    request.state.resultado = "logout"
    resposta = Response(status_code=204)
    apagar_cookie(resposta, request)
    return resposta
