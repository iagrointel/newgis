"""LDAP/Active Directory como provedor de login externo, por inquilino (item L0-08-d-ldap, filho de L0-08-sso;
ADR 0002 seção 13 "Gancho para SSO"; docs/adr/0008-ldap-ad.md tem o raciocínio completo). Módulo isolado: não
importa nem é importado por app/auth/rotas_login.py, exceto pela função `_abrir_sessao` que REAPROVEITA (não
duplica) a criação de sessão a partir do momento em que a credencial já foi validada — o mesmo caminho do login
local depois do bind, sem escrever de novo cookie/evento/política de sessão.

Fluxo de `POST /api/login/ldap`: resolve o provedor do inquilino (`plat.provedor_ldap_de`, pré-contexto, como
`plat.auth_login`) → recusa senha vazia SEM tocar o diretório (nunca um "unauthenticated bind" vira sessão) →
contador de força bruta em memória (por tenant+login, reaproveita `bloqueio_tentativas`/`bloqueio_minutos` da
política do PRÓPRIO inquilino) → bind de SERVIÇO opcional (ou anônimo) só para a BUSCA → busca por
`filtro_usuario` com o login sempre ESCAPADO (RFC 4515: sem isso, `*)(uid=*` vira filtro sempre-verdadeiro) →
exige exatamente 1 resultado → bind do USUÁRIO com a senha informada (a única prova de identidade) →
`memberOf` mapeado para perfil via `provedor_ldap.mapa_grupo_perfil` → upsert local (nunca grava a senha do
LDAP; `plat.ldap_provisionar` nunca sobrescreve conta de origem 'local' com o mesmo login) → `plat.auth_login`
de novo (mesmo formato do login local) → `_abrir_sessao`.

Nunca grava PLAT_LDAP_URL/PLAT_LDAP_BASE_DN (env) na tabela: são só o PADRÃO usado quando a linha do inquilino
não tem `url`/`base_dn` próprios (o diretório de teste desta máquina, um contêiner glauth efêmero, "aponta"
para o inquilino de demonstração exatamente assim, sem gravar nada específico de teste no banco)."""

import base64
import hashlib
import logging
import os
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import ldap3
import psycopg2
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Request, Response
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from pydantic import Field

from app import db, limites
from app.auth.comum import erro_do_banco, registrar_evento
from app.auth.modelos import LoginEntrada, Modelo, Saida
from app.auth.politica import politica_de
from app.auth.privilegios import ORDEM_PERFIL
from app.auth.rotas_login import _abrir_sessao  # reaproveita a criação de sessão do login local; ver docstring
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.settings import settings

log = logging.getLogger("plat.auth.ldap")
router = APIRouter(prefix="/api", tags=["login"])
PREFIXO_CIFRA = "encldap:v1:"
PERFIS_VALIDOS = ("admin", "editor", "visualizador", "campo")


# ---------------------------------------------------------------- cifra da senha de bind de serviço (nunca a
# senha do usuário do LDAP, que nunca é gravada em lugar nenhum): mesmo esquema AES-GCM de app/auth/totp.py,
# reimplementado aqui (não importado de lá) para o módulo ficar isolado; AAD própria evita reuso cruzado.
def _chave_cifra(plat_secret: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(plat_secret) + b"ldap-bind").digest()


def cifrar_bind_senha(senha: str, plat_secret: str) -> str:
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(_chave_cifra(plat_secret)).encrypt(nonce, senha.encode("utf-8"), b"plat-ldap-bind")
    return PREFIXO_CIFRA + base64.b64encode(nonce + cifrado).decode("ascii")


def decifrar_bind_senha(armazenado: str, plat_secret: str) -> str:
    if not armazenado or not armazenado.startswith(PREFIXO_CIFRA):
        raise ValueError("senha de bind sem o prefixo encldap:v1:")
    bruto = base64.b64decode(armazenado[len(PREFIXO_CIFRA) :])
    return AESGCM(_chave_cifra(plat_secret)).decrypt(bruto[:12], bruto[12:], b"plat-ldap-bind").decode("utf-8")


# ---------------------------------------------------------------- filtro de busca: o login do usuário É
# confiável (vem do corpo JSON), mas entra num filtro LDAP — sem escapar, `ana*)(uid=*` vira um filtro
# sempre-verdadeiro (RFC 4515 seção 3); é o ataque nomeado na refutação do item.
def montar_filtro(template: str, login: str) -> str:
    return template.replace("{login}", escape_filter_chars(login))


# ---------------------------------------------------------------- mapeamento de grupo -> perfil (D5 do
# L0_CONCEITO: vocabulário fechado de 4 perfis). Casa pela chave inteira (DN completo, como o LDAP devolve em
# memberOf) e, em segundo lugar, só pelo CN do primeiro RDN (para quem prefere configurar o mapa com o nome do
# grupo, sem o DN inteiro). Quando mais de um grupo mapeado bate, vale o perfil de MAIOR alcance (admin > editor
# > campo > visualizador, ORDEM_PERFIL de app/auth/privilegios.py — o mesmo vocabulário do resto da plataforma).
def perfil_por_grupos(valores_grupo: list[str], mapa: dict[str, Any], perfil_padrao: str | None) -> str | None:
    normalizado = {str(k).strip().lower(): v for k, v in (mapa or {}).items()}
    candidatos: list[str] = []
    for valor in valores_grupo:
        chave = str(valor).strip().lower()
        if chave in normalizado:
            candidatos.append(normalizado[chave])
            continue
        primeiro_rdn = chave.split(",", 1)[0]
        if "=" in primeiro_rdn:
            cn = primeiro_rdn.split("=", 1)[1].strip()
            if cn in normalizado:
                candidatos.append(normalizado[cn])
    candidatos = [c for c in candidatos if c in ORDEM_PERFIL]
    if not candidatos:
        return perfil_padrao if perfil_padrao in ORDEM_PERFIL else None
    return max(candidatos, key=lambda p: ORDEM_PERFIL[p])


# ---------------------------------------------------------------- contador de força bruta EM MEMÓRIA (por
# processo; a unidade sobe --workers 2, então o teto efetivo dobra — documentado, não escondido). Cobre também
# o login que ainda não existe localmente (a refutação do item testa 1.000 binds/min contra um login que pode
# nunca ter sido provisionado); reaproveita os MESMOS números da política de bloqueio local do inquilino
# (nunca um limiar novo): D6 do L0_CONCEITO já vale para "toda tentativa de credencial", não só senha local.
_FALHAS: dict[tuple[int, str], list[float]] = {}
_TRAVA_FALHAS = threading.Lock()


def _bind_bloqueado(tenant_id: int, login: str, janela_min: int, maximo: int) -> bool:
    chave = (tenant_id, login.strip().lower())
    agora = time.monotonic()
    with _TRAVA_FALHAS:
        vivas = [t for t in _FALHAS.get(chave, []) if agora - t < janela_min * 60]
        _FALHAS[chave] = vivas
        return len(vivas) >= maximo


def _registrar_falha_bind(tenant_id: int, login: str) -> None:
    chave = (tenant_id, login.strip().lower())
    with _TRAVA_FALHAS:
        _FALHAS.setdefault(chave, []).append(time.monotonic())


def _limpar_falhas_bind(tenant_id: int, login: str) -> None:
    _FALHAS.pop((tenant_id, login.strip().lower()), None)


# ---------------------------------------------------------------- resolução do endereço: a linha do inquilino
# manda; PLAT_LDAP_URL/PLAT_LDAP_BASE_DN (env) são só o padrão do diretório de TESTE desta máquina.
def _url_padrao() -> str | None:
    return (os.environ.get("PLAT_LDAP_URL") or "").strip() or None


def _base_dn_padrao() -> str | None:
    return (os.environ.get("PLAT_LDAP_BASE_DN") or "").strip() or None


class ErroLdap(Exception):
    """Erro de bind/busca traduzido para uma mensagem que NUNCA distingue 'usuário inexistente' de 'senha
    errada' de 'diretório fora do ar' no corpo devolvido ao cliente (só varia o log interno)."""

    def __init__(self, motivo_interno: str):
        self.motivo_interno = motivo_interno
        super().__init__(motivo_interno)


def _conectar(url: str, timeout: int) -> ldap3.Server:
    """Nunca deixa o ldap3 adivinhar host/porta/TLS a partir da string: parseada explicitamente aqui, o
    mesmo URL que o portão do item nomeia (PLAT_LDAP_URL/provedor_ldap.url) sempre vira host+porta+ssl."""
    partes = urlsplit(url)
    if partes.scheme not in ("ldap", "ldaps") or not partes.hostname:
        raise ErroLdap(f"url_invalida:{url}")
    usar_ssl = partes.scheme == "ldaps"
    porta = partes.port or (636 if usar_ssl else 389)
    return ldap3.Server(partes.hostname, port=porta, use_ssl=usar_ssl, connect_timeout=timeout, get_info=ldap3.NONE)


def _atributo(entrada, nome: str):
    """Leitura tolerante de um atributo de Entry do ldap3 (case-insensitive; devolve [] quando ausente,
    nunca levanta) — mais robusta que checar `entry_attributes` (a chave pode voltar com outra caixa)."""
    try:
        return list(entrada[nome].values)
    except Exception:  # noqa: BLE001 — LDAPKeyError e afins: atributo ausente na entrada
        return []


def autenticar_e_buscar_grupos(
    *,
    url: str,
    base_dn: str,
    start_tls: bool,
    bind_dn: str | None,
    bind_senha: str | None,
    filtro_usuario: str,
    atributo_grupos: str,
    login: str,
    senha: str,
    timeout: int = limites.LDAP_TIMEOUT_S,
) -> dict[str, Any]:
    """Faz TUDO num só lugar: bind de serviço (ou anônimo) → busca (exatamente 1) → bind do usuário → devolve
    {"dn", "nome", "email", "grupos": [...]}. Levanta ErroLdap em qualquer desvio (o chamador decide o 401)."""
    if not senha or not senha.strip():
        # nunca chega a abrir uma conexão: bind com senha vazia é "unauthenticated bind" (RFC 4513 §5.1.2) e
        # muitos servidores o aceitam como se fosse anônimo — a defesa é NUNCA tentar, não confiar no servidor
        # (o ldap3 já levanta LDAPPasswordIsMandatoryError sozinho para SIMPLE bind sem senha; não confiamos
        # só nisso, por isso o corte vem antes de qualquer conexão)
        raise ErroLdap("senha_vazia")
    try:
        return _autenticar_e_buscar_grupos_interno(
            url=url, base_dn=base_dn, start_tls=start_tls, bind_dn=bind_dn, bind_senha=bind_senha,
            filtro_usuario=filtro_usuario, atributo_grupos=atributo_grupos, login=login, senha=senha,
            timeout=timeout,
        )
    except ErroLdap:
        raise
    except LDAPException as e:
        # servidor fora do ar, recusou conexão, timeout, StartTLS não suportado etc: tudo vira "diretório
        # indisponível" para o chamador (nunca 500; nunca derruba o login local, que é outra rota)
        raise ErroLdap(f"ldap_indisponivel:{type(e).__name__}:{e}") from e


def _autenticar_e_buscar_grupos_interno(
    *, url: str, base_dn: str, start_tls: bool, bind_dn: str | None, bind_senha: str | None,
    filtro_usuario: str, atributo_grupos: str, login: str, senha: str, timeout: int,
) -> dict[str, Any]:
    servidor = _conectar(url, timeout)
    try:
        busca = ldap3.Connection(
            servidor,
            user=bind_dn,
            password=bind_senha,
            authentication=ldap3.SIMPLE if bind_dn else ldap3.ANONYMOUS,
            receive_timeout=timeout,
            auto_bind=False,
        )
        if start_tls and not url.lower().startswith("ldaps://"):
            try:
                busca.open()
                busca.start_tls()
            except LDAPException as e:
                raise ErroLdap(f"starttls_falhou:{e}") from e
        if not busca.bind():
            raise ErroLdap(f"bind_servico_falhou:{busca.result}")
        filtro = montar_filtro(filtro_usuario, login)
        ok = busca.search(
            search_base=base_dn,
            search_filter=filtro,
            search_scope=ldap3.SUBTREE,
            attributes=["cn", "displayName", "mail", atributo_grupos],
            size_limit=limites.LDAP_BUSCA_MAX + 1,
        )
        entradas = list(busca.entries) if ok else []
        if len(entradas) != limites.LDAP_BUSCA_MAX:
            raise ErroLdap(f"busca_nao_unica:{len(entradas)}")
        entrada = entradas[0]
        dn_usuario = str(entrada.entry_dn)
    finally:
        try:
            busca.unbind()
        except Exception:  # noqa: BLE001 — desligar a conexão de busca nunca deve mascarar o erro real
            pass
    autenticacao = ldap3.Connection(
        servidor, user=dn_usuario, password=senha, authentication=ldap3.SIMPLE, receive_timeout=timeout,
        auto_bind=False,
    )
    try:
        if start_tls and not url.lower().startswith("ldaps://"):
            autenticacao.open()
            autenticacao.start_tls()
        if not autenticacao.bind():
            raise ErroLdap(f"bind_usuario_falhou:{autenticacao.result}")
    finally:
        try:
            autenticacao.unbind()
        except Exception:  # noqa: BLE001
            pass

    def _valor(nome: str) -> str | None:
        v = _atributo(entrada, nome)
        return str(v[0]) if v else None

    return {
        "dn": dn_usuario,
        "nome": _valor("displayName") or _valor("cn") or login,
        "email": _valor("mail"),
        "grupos": [str(g) for g in _atributo(entrada, atributo_grupos)],
    }


# ================================================================== rota pública de login (POST /api/login/ldap)
def _provedor_de(tenant_slug: str) -> dict:
    with db.db() as cur:
        cur.execute("SELECT * FROM plat.provedor_ldap_de(%s)", (tenant_slug,))
        r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "inquilino_inexistente", "inquilino inexistente")
    return r


@router.post(
    "/login/ldap",
    response_model_exclude_unset=True,
    openapi_extra={"x-auth": "-", "x-privilegio": "publico"},
)
def login_ldap(corpo: LoginEntrada, request: Request, resposta: Response):
    tenant_slug = corpo.inquilino.strip().lower()
    login = corpo.login.strip()
    r = _provedor_de(tenant_slug)
    if not r["tenant_ativo"]:
        request.state.resultado = "suspenso"
        raise ErroAPI(503, "inquilino_suspenso", "inquilino suspenso; fale com o operador da plataforma")
    if not r["habilitado"]:
        request.state.resultado = "externo_desabilitado"
        raise ErroAPI(403, "login_ldap_desabilitado", "este inquilino não tem login por LDAP habilitado")
    politica = politica_de(r["config"], tenant_slug)  # mesma política (inclusive bloqueio) do login local
    if _bind_bloqueado(r["tenant_id"], login, politica.bloqueio_minutos, politica.bloqueio_tentativas):
        request.state.resultado = "bloqueado"
        raise ErroAPI(423, "bloqueado", "muitas tentativas; aguarde e tente de novo")
    url = r["url"] or _url_padrao()
    base_dn = r["base_dn"] or _base_dn_padrao()
    if not url or not base_dn:
        log.error("provedor LDAP do inquilino %s sem url/base_dn (nem provedor nem PLAT_LDAP_*)", tenant_slug)
        request.state.resultado = "sem_configuracao"
        raise ErroAPI(503, "ldap_sem_configuracao", "login por LDAP não está configurado neste inquilino")
    bind_senha = None
    if r["bind_dn"] and r["bind_senha_cifrada"]:
        try:
            bind_senha = decifrar_bind_senha(r["bind_senha_cifrada"], settings.PLAT_SECRET)
        except ValueError:
            log.error("senha de bind do provedor LDAP do inquilino %s ilegível (PLAT_SECRET trocado?)", tenant_slug)
            raise ErroAPI(503, "ldap_indisponivel", "diretório indisponível; tente o login local") from None
    try:
        achado = autenticar_e_buscar_grupos(
            url=url,
            base_dn=base_dn,
            start_tls=r["start_tls"],
            bind_dn=r["bind_dn"],
            bind_senha=bind_senha,
            filtro_usuario=r["filtro_usuario"],
            atributo_grupos=r["atributo_grupos"],
            login=login,
            senha=corpo.senha,
        )
    except ErroLdap as e:
        if e.motivo_interno.startswith(("bind_servico_falhou", "starttls_falhou", "ldap_indisponivel", "url_invalida")):
            # diretório fora do ar/mal configurado: NUNCA derruba o login local (portão do item); 503 aqui é só
            # desta rota — /api/login (local) continua respondendo normalmente, e o front pode tentar de novo
            log.warning("diretório LDAP do inquilino %s indisponível: %s", tenant_slug, e.motivo_interno)
            request.state.resultado = "diretorio_indisponivel"
            raise ErroAPI(503, "ldap_indisponivel", "diretório indisponível; tente o login local") from e
        _registrar_falha_bind(r["tenant_id"], login)
        request.state.resultado = "credenciais_invalidas"
        raise ErroAPI(401, "credenciais_invalidas", "inquilino, usuário ou senha inválidos") from e
    _limpar_falhas_bind(r["tenant_id"], login)
    perfil = perfil_por_grupos(achado["grupos"], r["mapa_grupo_perfil"] or {}, r["perfil_padrao"])
    if perfil is None:
        request.state.resultado = "sem_grupo_mapeado"
        raise ErroAPI(
            403,
            "sem_grupo_mapeado",
            "nenhum grupo do diretório está mapeado para um perfil desta plataforma; fale com o administrador",
        )
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT * FROM plat.ldap_provisionar(%s, %s, %s, %s, %s, %s, true)",
                (r["tenant_id"], login, achado["nome"], achado["email"], perfil, achado["dn"]),
            )
            prov = cur.fetchone()
            cur.execute("SELECT * FROM plat.auth_login(%s, %s)", (tenant_slug, login))
            linha = cur.fetchone()
    except psycopg2.errors.RaiseException as e:
        if (e.diag.message_primary or "").strip() == "login_em_uso_local":
            request.state.resultado = "login_em_uso_local"
            raise ErroAPI(
                409, "login_em_uso_local", "já existe uma conta local com este login; fale com o administrador"
            ) from e
        raise erro_do_banco(e) from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    ctx = db.Contexto(linha["tenant_id"], linha["usuario_id"], login)
    with db.db(ctx) as cur:
        registrar_evento(
            cur,
            request,
            "usuarios/criar" if prov["criado"] else "usuarios/atualizar",
            "usuario",
            linha["usuario_id"],
            {"origem": "ldap", "perfil": perfil, "perfil_anterior": prov["perfil_anterior"]},
        )
    politica_sessao = politica_de(linha["config"], tenant_slug)
    return _abrir_sessao(request, resposta, ctx, linha["usuario_id"], politica_sessao, "ldap", None)


# ================================================================== configuração do provedor por inquilino
# (GET/PUT /api/org/ldap; privilégio org.integracoes, o mesmo que a ADR 0002 já reservou para "SSO, SMTP,
# webhooks, CORS"). Nunca devolve a senha de bind cifrada nem em claro; PUT aceita `bind_senha` em claro só
# para cifrar e gravar (nunca ecoada de volta).
class ProvedorLdapEntrada(Modelo):
    habilitado: bool = True
    url: str | None = Field(default=None, max_length=250)
    base_dn: str | None = Field(default=None, max_length=250)
    start_tls: bool = True
    bind_dn: str | None = Field(default=None, max_length=250)
    bind_senha: str | None = Field(default=None, max_length=250)
    filtro_usuario: str = Field(default="(uid={login})", min_length=3, max_length=250)
    atributo_grupos: str = Field(default="memberOf", min_length=1, max_length=64)
    perfil_padrao: str | None = None
    mapa_grupo_perfil: dict[str, str] = Field(default_factory=dict)


class ProvedorLdapSaida(Saida):
    habilitado: bool
    url: str | None
    base_dn: str | None
    start_tls: bool
    bind_dn: str | None
    tem_bind_senha: bool
    filtro_usuario: str
    atributo_grupos: str
    perfil_padrao: str | None
    mapa_grupo_perfil: dict[str, Any]


def _provedor_saida(r: dict) -> dict:
    return {
        "habilitado": r["habilitado"],
        "url": r["url"],
        "base_dn": r["base_dn"],
        "start_tls": r["start_tls"],
        "bind_dn": r["bind_dn"],
        "tem_bind_senha": bool(r["bind_senha_cifrada"]),
        "filtro_usuario": r["filtro_usuario"],
        "atributo_grupos": r["atributo_grupos"],
        "perfil_padrao": r["perfil_padrao"],
        "mapa_grupo_perfil": r["mapa_grupo_perfil"] or {},
    }


@router.get(
    "/org/ldap",
    response_model=ProvedorLdapSaida | None,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"},
)
def org_ldap_ler(auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.provedor_ldap WHERE tenant_id = plat.tenant_atual()")
        r = cur.fetchone()
    return _provedor_saida(r) if r is not None else None


@router.put(
    "/org/ldap",
    response_model=ProvedorLdapSaida,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"},
)
def org_ldap_gravar(corpo: ProvedorLdapEntrada, request: Request, auth: Auth = autenticado("org.integracoes")):
    if corpo.perfil_padrao is not None and corpo.perfil_padrao not in PERFIS_VALIDOS:
        raise ErroAPI(422, "validacao", f"perfil_padrao precisa ser um de {PERFIS_VALIDOS}", {"campo": "perfil_padrao"})
    for grupo, perfil in corpo.mapa_grupo_perfil.items():
        if perfil not in PERFIS_VALIDOS:
            raise ErroAPI(
                422, "validacao", f"mapa_grupo_perfil[{grupo!r}] precisa ser um de {PERFIS_VALIDOS}",
                {"campo": "mapa_grupo_perfil", "grupo": grupo},
            )
    bind_senha_cifrada = None
    if corpo.bind_dn:
        if not corpo.bind_senha:
            with db.db(auth.contexto()) as cur:
                cur.execute(
                    "SELECT bind_senha_cifrada FROM plat.provedor_ldap WHERE tenant_id = plat.tenant_atual()"
                )
                anterior = cur.fetchone()
            bind_senha_cifrada = anterior["bind_senha_cifrada"] if anterior else None
        else:
            bind_senha_cifrada = cifrar_bind_senha(corpo.bind_senha, settings.PLAT_SECRET)
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                """
                INSERT INTO plat.provedor_ldap(tenant_id, habilitado, url, base_dn, start_tls, bind_dn,
                    bind_senha_cifrada, filtro_usuario, atributo_grupos, perfil_padrao, mapa_grupo_perfil,
                    criado_por, atualizado_por)
                VALUES (plat.tenant_atual(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    habilitado = EXCLUDED.habilitado, url = EXCLUDED.url, base_dn = EXCLUDED.base_dn,
                    start_tls = EXCLUDED.start_tls, bind_dn = EXCLUDED.bind_dn,
                    bind_senha_cifrada = EXCLUDED.bind_senha_cifrada, filtro_usuario = EXCLUDED.filtro_usuario,
                    atributo_grupos = EXCLUDED.atributo_grupos, perfil_padrao = EXCLUDED.perfil_padrao,
                    mapa_grupo_perfil = EXCLUDED.mapa_grupo_perfil, atualizado_por = EXCLUDED.atualizado_por,
                    atualizado_em = now()
                RETURNING *
                """,
                (
                    corpo.habilitado, corpo.url, corpo.base_dn, corpo.start_tls, corpo.bind_dn,
                    bind_senha_cifrada, corpo.filtro_usuario, corpo.atributo_grupos, corpo.perfil_padrao,
                    __import__("json").dumps(corpo.mapa_grupo_perfil), auth.usuario_id, auth.usuario_id,
                ),
            )
            r = cur.fetchone()
            registrar_evento(
                cur, request, "org/ldap_configurar", "provedor_ldap", r["id"], {"habilitado": r["habilitado"]}
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return _provedor_saida(r)


# ================================================================== importação em massa (opção do portão):
# cria usuários DESABILITADOS a partir dos membros de um grupo do diretório; ativam-se sozinhos no primeiro
# login bem-sucedido (plat.ldap_provisionar sempre grava ativo=true na hora do login).
class ImportarGrupoEntrada(Modelo):
    grupo_dn: str = Field(min_length=1, max_length=250)
    atributo_membro: str = Field(default="member", min_length=1, max_length=64)
    atributo_login: str = Field(default="uid", min_length=1, max_length=64)
    perfil: str


@router.post(
    "/org/ldap/importar",
    openapi_extra={"x-auth": "S/T", "x-privilegio": "org.integracoes"},
)
def org_ldap_importar(corpo: ImportarGrupoEntrada, request: Request, auth: Auth = autenticado("org.integracoes")):
    if corpo.perfil not in PERFIS_VALIDOS:
        raise ErroAPI(422, "validacao", f"perfil precisa ser um de {PERFIS_VALIDOS}", {"campo": "perfil"})
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT * FROM plat.provedor_ldap WHERE tenant_id = plat.tenant_atual()")
        r = cur.fetchone()
    if r is None or not r["habilitado"]:
        raise ErroAPI(409, "ldap_sem_configuracao", "configure o provedor LDAP antes de importar um grupo")
    url = r["url"] or _url_padrao()
    base_dn = r["base_dn"] or _base_dn_padrao()
    if not url or not base_dn:
        raise ErroAPI(503, "ldap_sem_configuracao", "login por LDAP não está configurado neste inquilino")
    bind_senha = decifrar_bind_senha(r["bind_senha_cifrada"], settings.PLAT_SECRET) if r["bind_senha_cifrada"] else None
    servidor = _conectar(url, limites.LDAP_TIMEOUT_S)
    conexao = ldap3.Connection(
        servidor, user=r["bind_dn"], password=bind_senha,
        authentication=ldap3.SIMPLE if r["bind_dn"] else ldap3.ANONYMOUS,
        receive_timeout=limites.LDAP_TIMEOUT_S, auto_bind=False,
    )
    try:
        if r["start_tls"] and not url.lower().startswith("ldaps://"):
            conexao.open()
            conexao.start_tls()
        if not conexao.bind():
            raise ErroAPI(503, "ldap_indisponivel", "não foi possível conectar ao diretório")
        ok = conexao.search(
            search_base=base_dn,
            search_filter=f"({escape_filter_chars(corpo.atributo_membro)}={escape_filter_chars(corpo.grupo_dn)})",
            search_scope=ldap3.SUBTREE,
            attributes=[corpo.atributo_login, "cn", "displayName", "mail"],
            size_limit=limites.LDAP_IMPORTAR_MAX,
        )
        entradas = list(conexao.entries) if ok else []
    finally:
        try:
            conexao.unbind()
        except Exception:  # noqa: BLE001
            pass
    usuarios = []
    for entrada in entradas:
        valores_login = _atributo(entrada, corpo.atributo_login)
        if not valores_login:
            continue
        login_valor = str(valores_login[0])
        valores_nome = _atributo(entrada, "displayName") or _atributo(entrada, "cn")
        nome_valor = str(valores_nome[0]) if valores_nome else login_valor
        valores_email = _atributo(entrada, "mail")
        usuarios.append(
            {
                "login": login_valor,
                "nome": nome_valor,
                "email": str(valores_email[0]) if valores_email else None,
                "sujeito_externo": str(entrada.entry_dn),
            }
        )
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                "SELECT * FROM plat.ldap_importar_lote(plat.tenant_atual(), %s::jsonb, %s)",
                (__import__("json").dumps(usuarios), corpo.perfil),
            )
            resultado = dict(cur.fetchone())
            registrar_evento(
                cur, request, "org/ldap_importar", "provedor_ldap", r["id"],
                {"grupo_dn": corpo.grupo_dn, "encontrados": len(entradas), **resultado},
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {"grupo_dn": corpo.grupo_dn, "encontrados": len(entradas), **resultado}
