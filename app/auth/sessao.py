"""Resolução de identidade por requisição (ADR 0002 seções 5, 8, 10): cookie `plat_sessao` OU `Authorization: Bearer`
(ambos = 400), pendências (5.4), CSRF por Origin + Content-Type sob cookie (5.3), restrições referer/IP e motivo
legível do 401 de token (8.1, 8.3), escopo (8.2), `X-Plat-Inquilino` só para superadmin em rota marcada (10).
Tudo o que a rota sabe sobre quem chama vive em `Auth`; o middleware lê `request.state.auth` para o log_acesso."""

import datetime
import hashlib
import ipaddress
import logging
import os
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from urllib.parse import urlsplit

import psycopg2
from fastapi import Depends, Request

from app import db, limite_taxa, limites
from app.auth import escopos as esc
from app.auth.politica import Politica, politica_de
from app.erros import ErroAPI
from app.settings import settings

log = logging.getLogger("plat.auth")
COOKIE = "plat_sessao"
TOKEN_PREFIXO = "plat_"
TOKEN_TAMANHO = 48
VERBOS_DE_ESCRITA = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ROTAS_COM_PENDENCIA = ("/api/eu", "/api/eu/senha", "/api/logout")
PREFIXOS_COM_PENDENCIA = ("/api/eu/2fa/",)


@dataclass
class Auth:
    modo: str  # sessao | token
    usuario_id: int
    tenant_id: int
    login: str
    nome: str
    email: str | None
    perfil: str
    superadmin: bool
    origem: str
    papel_id: int | None
    privilegios: list[str]
    trocar_senha: bool
    totp_ativo: bool
    tenant_slug: str
    tenant_nome: str
    config: dict
    politica: Politica
    pendencias: list[str] = field(default_factory=list)
    sessao_hash: str | None = None
    sessao: dict | None = None
    token_id: int | None = None
    token: dict | None = None
    escopos: list[str] = field(default_factory=list)
    leitura_inquilino: int | None = None  # X-Plat-Inquilino resolvido: contexto de leitura de OUTRO inquilino
    leitura_slug: str | None = None

    def contexto(self) -> db.Contexto:
        return db.Contexto(self.tenant_id, self.usuario_id, self.login)

    def contexto_leitura(self) -> db.Contexto:
        """Contexto do inquilino lido pelo superadmin; sem cabeçalho é o próprio."""
        if self.leitura_inquilino is None:
            return self.contexto()
        return db.Contexto(self.leitura_inquilino, self.usuario_id, self.login)

    def tem(self, privilegio: str) -> bool:
        return privilegio in self.privilegios


def sha256_hex(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def ajuste_de_teste(nome: str) -> float | None:
    """PLAT_TESTE_BLOQUEIO_MIN / PLAT_TESTE_OCIOSA_S: aceitas só em dev; em producao ignoradas com aviso."""
    valor = os.environ.get(nome, "").strip()
    if not valor:
        return None
    if settings.producao:
        log.warning("%s ignorada em producao", nome)
        return None
    try:
        return float(valor)
    except ValueError:
        log.warning("%s inválida: %r", nome, valor)
        return None


def ociosa_horas_padrao() -> float:
    teste = ajuste_de_teste("PLAT_TESTE_OCIOSA_S")
    if teste is not None:
        return teste / 3600.0
    return float(limites.AUTH_PADROES["sessao_ociosa_horas"][0])


def ip_de(request: Request) -> str | None:
    return request.client.host if request.client else None


def agente_de(request: Request) -> str:
    return request.headers.get("user-agent", "")[:200]


def iso(dt: datetime.datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def pendencias_de(trocar_senha: bool, totp_ativo: bool, origem: str, politica: Politica) -> list[str]:
    p = []
    if trocar_senha:
        p.append("trocar_senha")
    if origem == "local" and politica.exigir_2fa and not totp_ativo:
        p.append("configurar_2fa")
    return p


def _auth_de_sessao(r: dict, hash_sessao: str) -> Auth:
    politica = politica_de(r["config"], r["tenant_slug"])
    ociosa_ate = (r["ultimo_uso"] or r["criado_em"]) + datetime.timedelta(hours=float(r["ociosa_horas"]))
    return Auth(
        modo="sessao",
        usuario_id=r["usuario_id"],
        tenant_id=r["tenant_id"],
        login=r["login"],
        nome=r["nome"],
        email=r["email"],
        perfil=r["perfil"],
        superadmin=r["superadmin"],
        origem=r["origem"],
        papel_id=r["papel_id"],
        privilegios=list(r["privilegios"] or []),
        trocar_senha=r["trocar_senha"],
        totp_ativo=r["totp_ativo"],
        tenant_slug=r["tenant_slug"],
        tenant_nome=r["tenant_nome"],
        config=r["config"] or {},
        politica=politica,
        pendencias=pendencias_de(r["trocar_senha"], r["totp_ativo"], r["origem"], politica),
        sessao_hash=hash_sessao,
        sessao={
            "criado_em": iso(r["criado_em"]),
            "expira_em": iso(r["expira_em"]),
            "ociosa_ate": iso(ociosa_ate),
            "ip": r["ip"],
        },
    )


def _origem_permitida(origem: str, padroes: list[str]) -> bool:
    """`https://*.exemplo.gov.br` casa só subdomínios; a comparação é da ORIGEM (esquema + host + porta)."""
    o = urlsplit(origem)
    if not o.scheme or not o.hostname:
        return False
    host = o.hostname.lower()
    porta = o.port or (443 if o.scheme == "https" else 80)
    for padrao in padroes:
        p = urlsplit(padrao)
        if not p.scheme or not p.hostname or p.scheme != o.scheme:
            continue
        pporta = p.port or (443 if p.scheme == "https" else 80)
        if pporta != porta:
            continue
        phost = p.hostname.lower()
        if phost.startswith("*."):
            if host.endswith(phost[1:]) and host != phost[2:]:
                return True
        elif fnmatchcase(host, phost):
            return True
    return False


def _checar_restricao(request: Request, restricao: dict) -> str | None:
    """Devolve o código de recusa (referer_ausente, referer_nao_permitido, ip_nao_permitido) ou None."""
    ips = restricao.get("ip") or []
    if ips:
        ip = ip_de(request)
        try:
            endereco = ipaddress.ip_address(ip)
        except (ValueError, TypeError):
            return "ip_nao_permitido"
        permitido = False
        for faixa in ips:
            try:
                if endereco in ipaddress.ip_network(faixa, strict=False):
                    permitido = True
                    break
            except ValueError:
                continue
        if not permitido:
            return "ip_nao_permitido"
    referers = restricao.get("referer") or []
    if referers:
        origem = request.headers.get("origin") or request.headers.get("referer")
        if not origem:
            return "referer_ausente"
        if not _origem_permitida(origem, referers):
            return "referer_nao_permitido"
    return None


def _auth_de_token(request: Request, valor: str) -> Auth:
    if not valor.startswith(TOKEN_PREFIXO) or len(valor) != TOKEN_TAMANHO:
        raise ErroAPI(401, "token_invalido", "token de serviço inválido")
    h = sha256_hex(valor)
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.auth_token(%s, %s)", (h, ip_de(request)))
        r = cur.fetchone()
    if r is None:
        request.state.resultado = "invalido"
        raise ErroAPI(401, "token_invalido", "token de serviço inválido")
    request.state.token_id = r["token_id"]
    request.state.tenant_id = r["tenant_id"]
    request.state.usuario_id = r["usuario_id"]
    if r["revogado_em"] is not None:
        request.state.resultado = "revogado"
        raise ErroAPI(
            401, "token_revogado", f"token revogado em {iso(r['revogado_em'])}", {"revogado_em": iso(r["revogado_em"])}
        )
    if r["expira_em"] is not None and r["expira_em"] <= datetime.datetime.now(datetime.UTC):
        request.state.resultado = "expirado"
        raise ErroAPI(
            401, "token_expirado", f"token expirado em {iso(r['expira_em'])}", {"expira_em": iso(r["expira_em"])}
        )
    politica = politica_de(r["config"], r["tenant_slug"])
    pendencias = pendencias_de(r["trocar_senha"], r["totp_ativo"], r["origem"], politica)
    if pendencias:
        request.state.resultado = "pendencia"
        raise ErroAPI(401, "pendencia_do_usuario", "o dono do token tem pendência de conta", pendencias)
    recusa = _checar_restricao(request, r["restricao"] or {})
    if recusa:
        request.state.resultado = recusa.split("_")[0]
        raise ErroAPI(
            401,
            recusa,
            {
                "ip_nao_permitido": "IP fora da restrição do token",
                "referer_ausente": "o token exige cabeçalho Origin ou Referer",
                "referer_nao_permitido": "origem fora da restrição do token",
            }[recusa],
        )
    return Auth(
        modo="token",
        usuario_id=r["usuario_id"],
        tenant_id=r["tenant_id"],
        login=r["login"],
        nome=r["nome"],
        email=r["email"],
        perfil=r["perfil"],
        superadmin=r["superadmin"],
        origem=r["origem"],
        papel_id=r["papel_id"],
        privilegios=list(r["privilegios"] or []),
        trocar_senha=r["trocar_senha"],
        totp_ativo=r["totp_ativo"],
        tenant_slug=r["tenant_slug"],
        tenant_nome=r["tenant_nome"],
        config=r["config"] or {},
        politica=politica,
        pendencias=[],
        token_id=r["token_id"],
        escopos=list(r["escopos"] or []),
        token={
            "id": r["token_id"],
            "nome": r["token_nome"],
            "escopos": list(r["escopos"] or []),
            "expira_em": iso(r["expira_em"]),
        },
    )


def resolver(request: Request) -> Auth | None:
    """Auth da requisição (cache em request.state.auth) ou None quando não há credencial."""
    if getattr(request.state, "auth", None) is not None:
        return request.state.auth
    cookie = request.cookies.get(COOKIE)
    cabecalho = request.headers.get("authorization", "")
    bearer = cabecalho[7:].strip() if cabecalho.lower().startswith("bearer ") else None
    if cookie and bearer:
        raise ErroAPI(400, "autenticacao_ambigua", "use o cookie de sessão OU o cabeçalho Authorization, não os dois")
    if bearer:
        auth = _auth_de_token(request, bearer)
    elif cookie:
        h = sha256_hex(cookie)
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.auth_sessao(%s, %s)", (h, ociosa_horas_padrao()))
            r = cur.fetchone()
        if r is None:
            raise ErroAPI(401, "sessao_expirada", "sessão inexistente ou expirada; entre de novo")
        auth = _auth_de_sessao(r, h)
    else:
        return None
    request.state.auth = auth
    request.state.tenant_id = auth.tenant_id
    request.state.usuario_id = auth.usuario_id
    request.state.token_id = auth.token_id
    # camada 2 do item L7-03-b-rate-limit-abuso: limite de taxa por inquilino, aqui porque é o único ponto
    # por onde TODA requisição autenticada passa (sessão OU token), já com tenant_id e config resolvidos.
    limite_taxa.exigir(request, auth.tenant_id, auth.config, "api", "api_por_minuto")
    return auth


def checar_escrita_sob_cookie(request: Request) -> None:
    """CSRF em duas camadas (ADR 0002 seção 5.3): Origin igual à URL pública quando vem; corpo só JSON."""
    if request.method not in VERBOS_DE_ESCRITA:
        return
    origem = request.headers.get("origin")
    if origem and origem.rstrip("/").lower() != settings.PLAT_URL_PUBLICA.lower():
        raise ErroAPI(403, "origem_invalida", "origem da requisição não é a da plataforma")
    tem_corpo = request.headers.get("content-length", "0") not in ("", "0") or "transfer-encoding" in request.headers
    if tem_corpo:
        tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if tipo != "application/json":
            raise ErroAPI(415, "tipo_nao_aceito", "o corpo precisa ser application/json")


def _rota_admite_pendencia(caminho: str) -> bool:
    return caminho in ROTAS_COM_PENDENCIA or caminho.startswith(PREFIXOS_COM_PENDENCIA)


def _resolver_leitura_superadmin(request: Request, auth: Auth, superadmin_pode_ler: bool) -> None:
    slug = request.headers.get("x-plat-inquilino")
    if not slug:
        return
    if not auth.superadmin or auth.modo != "sessao":
        raise ErroAPI(403, "so_superadmin", "o cabeçalho X-Plat-Inquilino é só para operadores da plataforma")
    if not superadmin_pode_ler:
        raise ErroAPI(400, "cabecalho_nao_aceito", "esta rota não aceita X-Plat-Inquilino")
    try:
        with db.db() as cur:
            cur.execute("SELECT plat.plataforma_tenant_id(%s, %s) AS id", (auth.sessao_hash, slug))
            tid = cur.fetchone()["id"]
    except psycopg2.errors.RaiseException as e:
        raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente") from e
    auth.leitura_inquilino = tid
    auth.leitura_slug = slug
    # trilha obrigatória (L0-07-f): evento no inquilino lido, com o login do operador
    with db.db(auth.contexto_leitura()) as cur:
        cur.execute(
            "SELECT plat.evento_registrar('inquilinos/leitura_superadmin', 'rota', %s, %s::jsonb, %s, %s)",
            (
                request.url.path,
                __import__("json").dumps({"operador": auth.login, "metodo": request.method}),
                ip_de(request),
                getattr(request.state, "req_id", None),
            ),
        )


def autenticado(
    privilegio: str | None = None,
    *,
    escopo_token: str | None = "admin:inquilino",
    so_sessao: bool = False,
    permitir_pendencia: bool = False,
    superadmin_pode_ler: bool = False,
    superadmin: bool = False,
):
    """Fábrica de dependência. Ordem: credencial → só sessão? → CSRF sob cookie → X-Plat-Inquilino → pendências →
    escopo do token → privilégio → superadmin (404, não 403, para não confirmar a rota)."""

    def dependencia(request: Request) -> Auth:
        auth = resolver(request)
        if auth is None:
            if superadmin:
                raise ErroAPI(404, "nao_encontrado", "recurso inexistente")
            raise ErroAPI(401, "nao_autenticado", "entre para continuar")
        if superadmin and not (auth.superadmin and auth.modo == "sessao"):
            raise ErroAPI(404, "nao_encontrado", "recurso inexistente")
        if so_sessao and auth.modo == "token":
            raise ErroAPI(403, "so_sessao", "esta operação exige sessão de usuário, não token de serviço")
        if auth.modo == "sessao":
            checar_escrita_sob_cookie(request)
        _resolver_leitura_superadmin(request, auth, superadmin_pode_ler)
        if auth.pendencias and not permitir_pendencia and not _rota_admite_pendencia(request.url.path):
            raise ErroAPI(403, "pendencia", "resolva a pendência da conta para continuar", auth.pendencias)
        if auth.modo == "token" and escopo_token:
            esc.exigir_escopo(auth, escopo_token)
        if privilegio and not auth.tem(privilegio):
            raise ErroAPI(403, "sem_privilegio", f"a operação exige o privilégio {privilegio}", {"exigido": privilegio})
        return auth

    return Depends(dependencia)


def exigir(privilegio: str, **opcoes):
    return autenticado(privilegio, **opcoes)


def opcional(request: Request) -> Auth | None:
    """Para rotas públicas que se comportam diferente com sessão (página inicial): nunca levanta por ausência."""
    try:
        return resolver(request)
    except ErroAPI:
        return None
