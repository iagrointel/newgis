"""Tela e API 'Logins' (item L0-08-e-mapeamento-provisionamento): os provedores de login externo do inquilino
(LDAP único, OIDC e SAML vários) numa lista só, com rótulo e ordem dos botões da tela de entrada, habilitação e as
regras de provisionamento (app/auth/provisionamento.py) — criação automática ou só por convite, padrões para
membro novo, mapa valor do IdP -> perfil/papel/grupos internos, atualização a cada login, desligamento sem grupo
mapeado. O `perfil` de cada regra é copiado para `mapa_grupo_perfil` do provedor (a regra de perfil que já existia
em ldap/oidc/saml continua sendo a fonte), então nunca há dois mapas divergentes. Também 'desregistrar' uma conta
federada: o vínculo com o IdP é removido e a conta desativada (a conta continua no IdP; volta em modo automático
no próximo login, ou só com novo convite em modo convite). Privilégio `org.integracoes`, só sessão."""

import json
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app import db
from app.auth import provisionamento
from app.auth.comum import registrar_evento, usuario_ou_404
from app.auth.modelos import Modelo, Saida
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["logins"])
PRIV = {"x-auth": "S", "x-privilegio": "org.integracoes"}
TIPOS = ("ldap", "oidc", "saml")
TABELA = {"ldap": "plat.provedor_ldap", "oidc": "plat.provedor_oidc", "saml": "plat.provedor_saml"}


class LoginEntrada(Modelo):
    habilitado: bool | None = None
    rotulo: str | None = Field(default=None, min_length=1, max_length=120)
    ordem: int | None = Field(default=None, ge=0, le=99)
    provisionamento: dict[str, Any] | None = None


class LoginProvedor(Saida):
    tipo: str
    id: int
    habilitado: bool
    rotulo: str | None
    ordem: int | None
    identificador: str | None
    provisionamento: dict[str, Any]
    atualizado_em: str | None


class Logins(Saida):
    provedores: list[LoginProvedor]
    criacoes: list[str]
    perfis: list[str]


def _linha(tipo: str, r: dict) -> dict:
    regras = provisionamento.regras_de(r.get("provisionamento") or {})
    return {
        "tipo": tipo,
        "id": r["id"],
        "habilitado": r["habilitado"],
        "rotulo": r.get("rotulo"),
        "ordem": r.get("ordem"),
        "identificador": r.get("identificador"),
        "perfil_padrao": r.get("perfil_padrao"),
        "mapa_grupo_perfil": r.get("mapa_grupo_perfil") or {},
        "atributo_grupos": r.get("atributo_grupos"),
        "provisionamento": provisionamento.para_json(regras),
        "atualizado_em": iso(r["atualizado_em"]) if r.get("atualizado_em") else None,
    }


def _listar(cur, auth: Auth) -> list[dict]:
    saida = []
    cur.execute(
        "SELECT tenant_id AS id, habilitado, url AS identificador, perfil_padrao, mapa_grupo_perfil, atributo_grupos, "
        "provisionamento, atualizado_em FROM plat.provedor_ldap WHERE tenant_id = %s",
        (auth.tenant_id,),
    )
    for r in cur.fetchall():
        saida.append(_linha("ldap", dict(r)))
    cur.execute(
        "SELECT id, habilitado, rotulo, ordem, issuer AS identificador, perfil_padrao, mapa_grupo_perfil, "
        "atributo_grupos, provisionamento, atualizado_em FROM plat.provedor_oidc ORDER BY ordem, id"
    )
    for r in cur.fetchall():
        saida.append(_linha("oidc", dict(r)))
    cur.execute(
        "SELECT id, habilitado, rotulo, ordem, idp_entity_id AS identificador, perfil_padrao, mapa_grupo_perfil, "
        "atributo_grupos, provisionamento, atualizado_em FROM plat.provedor_saml ORDER BY ordem, id"
    )
    for r in cur.fetchall():
        saida.append(_linha("saml", dict(r)))
    return saida


@router.get("/org/logins", response_model=Logins, openapi_extra=PRIV)
def listar(auth: Auth = autenticado("org.integracoes", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        provedores = _listar(cur, auth)
    return {
        "provedores": provedores,
        "criacoes": list(provisionamento.CRIACOES),
        "perfis": list(provisionamento.PERFIS_VALIDOS),
    }


@router.put("/org/logins/{tipo}/{id}", response_model=LoginProvedor, openapi_extra=PRIV)
def configurar(
    tipo: str,
    id: int,
    corpo: LoginEntrada,
    request: Request,
    auth: Auth = autenticado("org.integracoes", so_sessao=True),
):
    """Rótulo, ordem, habilitação e regras de provisionamento de um provedor; para `ldap` o id é o do inquilino
    (único). Papel e grupos citados têm de existir neste inquilino (422 nomeando o que falta)."""
    if tipo not in TIPOS:
        raise ErroAPI(404, "provedor_inexistente", "provedor inexistente")
    if corpo.provisionamento is None and corpo.habilitado is None and corpo.rotulo is None and corpo.ordem is None:
        raise ErroAPI(422, "validacao", "informe ao menos um campo")
    if tipo == "ldap" and (corpo.rotulo is not None or corpo.ordem is not None):
        raise ErroAPI(
            422, "validacao", "o provedor LDAP não tem botão próprio (rótulo/ordem não se aplicam)", {"campo": "rotulo"}
        )
    chave = "tenant_id" if tipo == "ldap" else "id"
    alvo = auth.tenant_id if tipo == "ldap" else id
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT id FROM {TABELA[tipo]} WHERE {chave} = %s", (alvo,))  # noqa: S608 — tabela de lista fixa
        if cur.fetchone() is None or (tipo == "ldap" and id not in (0, auth.tenant_id)):
            raise ErroAPI(404, "provedor_inexistente", "provedor inexistente")
        campos, valores = [], []
        propriedades: dict[str, Any] = {"tipo": tipo, "id": alvo}
        if corpo.habilitado is not None:
            campos.append("habilitado = %s")
            valores.append(corpo.habilitado)
            propriedades["habilitado"] = corpo.habilitado
        if corpo.rotulo is not None:
            campos.append("rotulo = %s")
            valores.append(corpo.rotulo.strip())
            propriedades["rotulo"] = corpo.rotulo.strip()
        if corpo.ordem is not None:
            campos.append("ordem = %s")
            valores.append(corpo.ordem)
            propriedades["ordem"] = corpo.ordem
        if corpo.provisionamento is not None:
            regras = provisionamento.regras_de(corpo.provisionamento)
            provisionamento.validar_no_inquilino(cur, regras)
            campos.append("provisionamento = %s::jsonb")
            valores.append(json.dumps(provisionamento.para_json(regras)))
            # o perfil de cada regra é a fonte do mapa de perfil do provedor (mesma chave = valor do IdP)
            campos.append("mapa_grupo_perfil = %s::jsonb")
            valores.append(json.dumps(regras.perfis()))
            propriedades["provisionamento"] = {
                "criacao": regras.criacao,
                "atualizar_a_cada_login": regras.atualizar_a_cada_login,
                "desligar_sem_grupo": regras.desligar_sem_grupo,
                "regras": len(regras.mapa),
            }
        campos.append("atualizado_em = now()")
        cur.execute(
            f"UPDATE {TABELA[tipo]} SET {', '.join(campos)} WHERE {chave} = %s",  # noqa: S608 — colunas fixas
            [*valores, alvo],
        )
        registrar_evento(cur, request, "org/logins_configurar", "provedor", f"{tipo}:{alvo}", propriedades)
        provedores = _listar(cur, auth)
    return next(p for p in provedores if p["tipo"] == tipo and p["id"] == alvo)


@router.post(
    "/usuarios/{id}/desregistrar",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S", "x-privilegio": "membros.gerir"},
)
def desregistrar(id: int, request: Request, auth: Auth = autenticado("membros.gerir", so_sessao=True)):
    """Conta federada (ldap/oidc/saml): remove o vínculo com o IdP e desativa; sessões caem; a conta no IdP
    continua. Conta local = 409. Em modo automático o próximo login religa; em modo convite exige novo convite."""
    with db.db(auth.contexto()) as cur:
        alvo = usuario_ou_404(cur, id)
        if alvo["origem"] == "local":
            raise ErroAPI(409, "conta_local", "só contas federadas (ldap/oidc/saml) se desregistram")
        if id == auth.usuario_id:
            raise ErroAPI(409, "conta_propria", "não é possível desregistrar a própria conta")
        cur.execute("UPDATE plat.usuario SET ativo = false, sujeito_externo = NULL WHERE id = %s", (id,))
        cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, NULL)", (id,))
        registrar_evento(cur, request, "usuarios/desregistrar", "usuario", id, {"origem": alvo["origem"]})
    return Response(status_code=204)
