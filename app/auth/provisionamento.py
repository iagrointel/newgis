"""Regras de provisionamento por provedor de login externo (item L0-08-e-mapeamento-provisionamento), o mesmo
laço para LDAP, OIDC e SAML depois que o IdP confirmou a identidade e antes de abrir a sessão:

    provedor.provisionamento = {
      "criacao": "automatica" | "convite",     # membro novo entra sozinho ou só com convite prévio (e-mail)
      "atualizar_a_cada_login": true,          # perfil/papel/grupos reaplicados a cada login (false = só na criação)
      "desligar_sem_grupo": false,             # conta existente sem grupo mapeado e sem perfil padrão -> desativada
      "padrao": {"papel_id": null, "grupos": ["<uuid>"], "pasta": "Pessoal de {login}"},   # membro novo sem regra
      "mapa": {"gis-editores": {"perfil": "editor", "papel_id": 3, "grupos": ["<uuid>"]}}  # valor EXATO do IdP
    }

O perfil (admin/editor/visualizador/campo) continua vindo de `mapa_grupo_perfil`/`perfil_padrao` das tabelas de
provedor (app/auth/ldap.py::perfil_por_grupos); a tela Logins grava as duas coisas de uma vez, com o `perfil` de
cada regra copiado para `mapa_grupo_perfil`. Mapeamento é por regra explícita: um grupo do IdP chamado
'administrador' sem regra não vira nada (refutação do item). Só as funções SECURITY DEFINER da migração
20260908T0212 escrevem; este módulo decide.

Esri 11.4, paridade (New member defaults · SAML/OIDC group membership): criar automaticamente × só convidados
= `criacao`; user type/role padrão = `perfil_padrao` + `padrao.papel_id`; groups padrão = `padrao.grupos`;
"update profile at sign-in" = `atualizar_a_cada_login`; vínculo grupo do IdP -> grupo interno por valor exato
= `mapa[valor].grupos`; sincronização de membros a cada login = os grupos citados nas regras são regidos (entra
e sai). Sem equivalente na Esri (extras daqui): `desligar_sem_grupo` e `pasta`."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from app import limites
from app.erros import ErroAPI

# importações tardias de app.db e app.auth.ldap (carregam a configuração): as decisões puras deste módulo rodam
# em teste de unidade sem .env
PERFIS_VALIDOS = ("admin", "editor", "visualizador", "campo")

log = logging.getLogger("plat.provisionamento")
CRIACOES = ("automatica", "convite")
MSG_SEM_GRUPO = "nenhum grupo do provedor está mapeado para um perfil desta plataforma; fale com o administrador"
MSG_CONVITE = "este provedor só aceita membros convidados; peça um convite ao administrador do inquilino"
MSG_DESLIGADA = "a conta foi desativada porque o provedor deixou de informar um grupo mapeado; fale com o administrador"


@dataclass
class Regra:
    perfil: str | None = None
    papel_id: int | None = None
    grupos: list[str] = field(default_factory=list)


@dataclass
class Regras:
    criacao: str = "automatica"
    atualizar_a_cada_login: bool = True
    desligar_sem_grupo: bool = False
    padrao: Regra = field(default_factory=Regra)
    pasta: str | None = None
    mapa: dict[str, Regra] = field(default_factory=dict)

    @property
    def regidos(self) -> list[str]:
        """Todos os grupos internos citados nas regras (padrão + mapa): são os que o provedor governa."""
        vistos: list[str] = []
        for r in [self.padrao, *self.mapa.values()]:
            for g in r.grupos:
                if g not in vistos:
                    vistos.append(g)
        return vistos

    def perfis(self) -> dict[str, str]:
        return {valor: r.perfil for valor, r in self.mapa.items() if r.perfil}


@dataclass
class Decisao:
    perfil: str | None
    papel_id: int | None
    grupos: list[str]
    pasta: str | None
    valores_casados: list[str]


def _uuid(valor: Any) -> str | None:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError, AttributeError):
        return None


def _regra(bruto: Any, campo: str) -> Regra:
    if not isinstance(bruto, dict):
        raise ErroAPI(422, "validacao", f"{campo} precisa ser um objeto", {"campo": campo})
    perfil = bruto.get("perfil")
    if perfil is not None and perfil not in PERFIS_VALIDOS:
        raise ErroAPI(422, "validacao", f"{campo}.perfil precisa ser um de {PERFIS_VALIDOS}", {"campo": campo})
    papel_id = bruto.get("papel_id")
    if papel_id is not None and (not isinstance(papel_id, int) or isinstance(papel_id, bool) or papel_id <= 0):
        raise ErroAPI(422, "validacao", f"{campo}.papel_id precisa ser inteiro positivo", {"campo": campo})
    grupos_brutos = bruto.get("grupos") or []
    if not isinstance(grupos_brutos, list) or len(grupos_brutos) > limites.PROVISIONAMENTO_GRUPOS_POR_REGRA:
        raise ErroAPI(422, "validacao", f"{campo}.grupos precisa ser lista de até "
                      f"{limites.PROVISIONAMENTO_GRUPOS_POR_REGRA} identificadores", {"campo": campo})
    grupos = []
    for g in grupos_brutos:
        u = _uuid(g)
        if u is None:
            raise ErroAPI(422, "validacao", f"{campo}.grupos contém identificador inválido", {"campo": campo})
        if u not in grupos:
            grupos.append(u)
    return Regra(perfil=perfil, papel_id=papel_id, grupos=grupos)


def regras_de(bruto: dict | None) -> Regras:
    """Normaliza e valida a forma (422 com o campo); a existência de papel/grupos no inquilino é conferida pela
    rota que grava (validar_no_inquilino) e, no login, ignorada com segurança pela função do banco."""
    b = bruto or {}
    if not isinstance(b, dict):
        raise ErroAPI(422, "validacao", "provisionamento precisa ser um objeto", {"campo": "provisionamento"})
    criacao = b.get("criacao") or "automatica"
    if criacao not in CRIACOES:
        raise ErroAPI(422, "validacao", f"criacao precisa ser um de {CRIACOES}", {"campo": "criacao"})
    for chave in ("atualizar_a_cada_login", "desligar_sem_grupo"):
        if chave in b and not isinstance(b[chave], bool):
            raise ErroAPI(422, "validacao", f"{chave} precisa ser booleano", {"campo": chave})
    padrao = _regra(b.get("padrao") or {}, "padrao")
    pasta = b.get("pasta")
    if pasta is not None and (not isinstance(pasta, str) or len(pasta) > 128 or "/" in pasta or "\\" in pasta):
        raise ErroAPI(422, "validacao", "pasta precisa ser texto de até 128 caracteres, sem barras", {"campo": "pasta"})
    mapa_bruto = b.get("mapa") or {}
    if not isinstance(mapa_bruto, dict) or len(mapa_bruto) > limites.PROVISIONAMENTO_REGRAS_MAX:
        raise ErroAPI(422, "validacao", f"mapa precisa ser objeto com até {limites.PROVISIONAMENTO_REGRAS_MAX} regras",
                      {"campo": "mapa"})
    mapa: dict[str, Regra] = {}
    for valor, regra in mapa_bruto.items():
        chave = str(valor).strip()
        if not chave or len(chave) > limites.PROVISIONAMENTO_VALOR_MAX:
            raise ErroAPI(422, "validacao", "valor de grupo do IdP vazio ou longo demais", {"campo": "mapa"})
        mapa[chave] = _regra(regra, f"mapa[{chave}]")
    return Regras(
        criacao=criacao,
        atualizar_a_cada_login=b.get("atualizar_a_cada_login", True),
        desligar_sem_grupo=b.get("desligar_sem_grupo", False),
        padrao=padrao,
        pasta=(pasta or "").strip() or None,
        mapa=mapa,
    )


def para_json(regras: Regras) -> dict:
    return {
        "criacao": regras.criacao,
        "atualizar_a_cada_login": regras.atualizar_a_cada_login,
        "desligar_sem_grupo": regras.desligar_sem_grupo,
        "padrao": {"papel_id": regras.padrao.papel_id, "grupos": regras.padrao.grupos},
        "pasta": regras.pasta,
        "mapa": {v: {"perfil": r.perfil, "papel_id": r.papel_id, "grupos": r.grupos} for v, r in regras.mapa.items()},
    }


def validar_no_inquilino(cur, regras: Regras) -> None:
    """Papel e grupos citados existem no inquilino da sessão (cursor já no contexto): 422 nomeando o que falta."""
    papeis = {r.papel_id for r in [regras.padrao, *regras.mapa.values()] if r.papel_id}
    if papeis:
        cur.execute("SELECT id FROM plat.papel_personalizado WHERE id = ANY(%s)", (list(papeis),))
        achados = {r["id"] for r in cur.fetchall()}
        if papeis - achados:
            raise ErroAPI(422, "validacao", f"papel inexistente neste inquilino: {sorted(papeis - achados)}",
                          {"campo": "papel_id"})
    grupos = set(regras.regidos)
    if grupos:
        cur.execute("SELECT id::text AS id FROM plat.grupo WHERE id = ANY(%s::uuid[])", (list(grupos),))
        achados = {r["id"] for r in cur.fetchall()}
        if grupos - achados:
            raise ErroAPI(422, "validacao", f"grupo inexistente neste inquilino: {sorted(grupos - achados)}",
                          {"campo": "grupos"})


def valores_do_idp(grupos: Any) -> list[str]:
    """Lista de valores do atributo de grupos como o IdP mandou, cortada em PROVISIONAMENTO_GRUPOS_IDP_MAX (um
    IdP hostil com milhares de grupos não custa mais que isso) e sem valores longos demais."""
    if grupos is None:
        return []
    if isinstance(grupos, str):
        grupos = [grupos]
    saida = []
    for v in list(grupos)[: limites.PROVISIONAMENTO_GRUPOS_IDP_MAX]:
        s = str(v).strip()
        if s and len(s) <= limites.PROVISIONAMENTO_VALOR_MAX:
            saida.append(s)
    return saida


def decidir(regras: Regras, valores: list[str], mapa_grupo_perfil: dict | None, perfil_padrao: str | None) -> Decisao:
    """Perfil pela regra já existente (perfil_por_grupos, mais o perfil de cada regra do mapa); papel e grupos
    pelas regras casadas por valor EXATO; sem regra casada = padrão. Nunca por nome parecido com papel."""
    from app.auth.ldap import perfil_por_grupos

    mapa_perfil = {**(mapa_grupo_perfil or {}), **regras.perfis()}
    perfil = perfil_por_grupos(valores, mapa_perfil, perfil_padrao)
    casados = [v for v in valores if v in regras.mapa]
    if casados:
        papel = next((regras.mapa[v].papel_id for v in casados if regras.mapa[v].papel_id), None)
        grupos: list[str] = []
        for v in casados:
            for g in regras.mapa[v].grupos:
                if g not in grupos:
                    grupos.append(g)
    else:
        papel = regras.padrao.papel_id
        grupos = list(regras.padrao.grupos)
    return Decisao(perfil=perfil, papel_id=papel, grupos=grupos, pasta=regras.pasta, valores_casados=casados)


def aplicar(
    request: Request,
    origem: str,
    provedor_id: int,
    tenant_id: int,
    tenant_slug: str,
    login: str,
    nome: str,
    email: str | None,
    grupos_idp: Any,
    sujeito_externo: str,
    mapa_grupo_perfil: dict | None,
    perfil_padrao: str | None,
) -> dict:
    """Depois do IdP dizer quem é: decide, provisiona (plat.usuario_externo_provisionar), aplica regras e
    devolve {linha: plat.auth_login, criado, perfil, perfil_anterior, efeitos, convite_id}. Levanta ErroAPI 403
    (sem_grupo_mapeado, convite_necessario, conta_desligada) ou 409 (login_em_uso_local)."""
    from app import db

    with db.db() as cur:
        cur.execute("SELECT plat.provisionamento_de(%s, %s) AS p", (origem, provedor_id))
        regras = regras_de(cur.fetchone()["p"] or {})
        cur.execute(
            "SELECT * FROM plat.usuario_federado_localizar(%s, %s, %s, %s)",
            (tenant_id, origem, login, sujeito_externo),
        )
        existente = cur.fetchone()
    valores = valores_do_idp(grupos_idp)
    decisao = decidir(regras, valores, mapa_grupo_perfil, perfil_padrao)
    # conta existente da mesma origem: desregistrada (vínculo removido) conta como 'nova' para o modo convite
    conhecida = existente is not None and existente["origem"] == origem and existente["sujeito_externo"] is not None
    convite = None
    if decisao.perfil is None and not (not conhecida and regras.criacao == "convite"):
        if conhecida and regras.desligar_sem_grupo:
            with db.db() as cur:
                cur.execute("SELECT plat.usuario_federado_desligar(%s, %s)", (tenant_id, existente["id"]))
            _evento_pre_contexto(cur_ctx(tenant_id, existente["id"], login), request, "usuarios/desligar_federado",
                                 existente["id"], {"origem": origem, "valores": valores[:20]})
            request.state.resultado = "conta_desligada"
            raise ErroAPI(403, "conta_desligada", MSG_DESLIGADA)
        request.state.resultado = "sem_grupo_mapeado"
        raise ErroAPI(403, "sem_grupo_mapeado", MSG_SEM_GRUPO)
    if not conhecida and regras.criacao == "convite":
        if email:
            with db.db() as cur:
                cur.execute("SELECT * FROM plat.convite_pendente_por_email(%s, %s)", (tenant_id, email))
                convite = cur.fetchone()
        if convite is None:
            request.state.resultado = "convite_necessario"
            raise ErroAPI(403, "convite_necessario", MSG_CONVITE)
        if decisao.perfil is None or not decisao.valores_casados:
            # convite manda quando o IdP não trouxe regra casada: perfil e papel do convite
            decisao.perfil = decisao.perfil if decisao.valores_casados else convite["perfil"]
            decisao.papel_id = decisao.papel_id if decisao.valores_casados else convite["papel_id"]
        if decisao.perfil is None:
            request.state.resultado = "sem_grupo_mapeado"
            raise ErroAPI(403, "sem_grupo_mapeado", MSG_SEM_GRUPO)
    atualizar = (not conhecida) or regras.atualizar_a_cada_login
    perfil = decisao.perfil if atualizar else existente["perfil"]
    with db.db() as cur:
        cur.execute(
            "SELECT * FROM plat.usuario_externo_provisionar(%s, %s, %s, %s, %s, %s, %s, true)",
            (tenant_id, origem, login, nome, email, perfil, sujeito_externo),
        )
        prov = cur.fetchone()
        efeitos = None
        if atualizar:
            cur.execute(
                "SELECT plat.usuario_federado_regras(%s, %s, %s, %s::uuid[], %s::uuid[], %s, %s) AS e",
                (
                    tenant_id,
                    prov["usuario_id"],
                    decisao.papel_id,
                    decisao.grupos,
                    regras.regidos,
                    decisao.pasta if prov["criado"] else None,
                    login,
                ),
            )
            efeitos = cur.fetchone()["e"]
        if convite is not None:
            cur.execute("SELECT plat.convite_consumir_federado(%s, %s)", (convite["id"], prov["usuario_id"]))
        cur.execute("SELECT * FROM plat.auth_login(%s, %s)", (tenant_slug, login))
        linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(401, "token_invalido", "não foi possível concluir o login pela organização")
    return {
        "linha": linha,
        "criado": prov["criado"],
        "perfil": perfil,
        "perfil_anterior": prov["perfil_anterior"],
        "efeitos": efeitos,
        "convite_id": str(convite["id"]) if convite else None,
        "valores_casados": decisao.valores_casados,
    }


def cur_ctx(tenant_id: int, usuario_id: int, login: str):
    from app import db

    return db.Contexto(tenant_id, usuario_id, login)


def _evento_pre_contexto(ctx, request: Request, tipo: str, alvo_id: int, propriedades: dict) -> None:
    from app import db
    from app.auth.comum import registrar_evento

    with db.db(ctx) as cur:
        registrar_evento(cur, request, tipo, "usuario", alvo_id, propriedades)


def registrar_efeitos(cur, request: Request, resultado: dict, origem: str, usuario_id: int) -> None:
    """Evento `usuarios/regras_aplicadas` quando o login mudou papel, grupos ou criou pasta (contexto do usuário)."""
    from app.auth.comum import registrar_evento

    e = resultado.get("efeitos") or {}
    if not e:
        return
    if e.get("grupos_entrou") or e.get("grupos_saiu") or e.get("pasta_criada") or resultado.get("convite_id"):
        registrar_evento(cur, request, "usuarios/regras_aplicadas", "usuario", usuario_id, {
            "origem": origem,
            "papel_id": e.get("papel_id"),
            "grupos_entrou": e.get("grupos_entrou") or [],
            "grupos_saiu": e.get("grupos_saiu") or [],
            "pasta_criada": bool(e.get("pasta_criada")),
            "convite_id": resultado.get("convite_id"),
            "valores": (resultado.get("valores_casados") or [])[:20],
        })


def resumo(regras: Regras) -> str:
    """Uma linha para a tela Logins."""
    return json.dumps(para_json(regras), ensure_ascii=False)[:200]
