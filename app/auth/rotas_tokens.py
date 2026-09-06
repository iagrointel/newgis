"""Tokens de serviço (ADR 0002 seção 8): só sob sessão (um token não se perpetua); escopos fechados; restrição
referer/IP; validade padrão 90 d, máxima 365 d (400 acima; 0 só em dev, para provar o 401 token_expirado);
revogação sem cache; rotação com 24 h de sobreposição; log dos acessos do token."""

import ipaddress
import secrets
from urllib.parse import urlsplit

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db, limites
from app.auth import escopos as esc
from app.auth.comum import erro_do_banco, paginacao, registrar_evento
from app.auth.modelos import Pagina, Token, TokenCriado, TokenCriar
from app.auth.sessao import Auth, autenticado, iso, sha256_hex
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/api/tokens", tags=["tokens"])
SQL_TOKEN = """
SELECT k.id, k.nome, k.prefixo, k.escopos, k.restricao, k.criado_em, k.expira_em, k.revogado_em, k.ultimo_uso,
       k.ultimo_ip, k.usos, k.renovado_por, k.usuario_id, u.login AS dono_login
FROM plat.token_servico k JOIN plat.usuario u ON u.id = k.usuario_id
"""


def _json(r: dict) -> dict:
    return {
        "id": r["id"],
        "nome": r["nome"],
        "prefixo": r["prefixo"],
        "escopos": list(r["escopos"] or []),
        "restricao": r["restricao"] or {},
        "criado_em": iso(r["criado_em"]),
        "expira_em": iso(r["expira_em"]),
        "revogado_em": iso(r["revogado_em"]),
        "ultimo_uso": iso(r["ultimo_uso"]),
        "ultimo_ip": r["ultimo_ip"],
        "usos": r["usos"],  # item L7-08-d: contagem alimentada pela mesma linha que grava ultimo_uso
        "dono": {"id": r["usuario_id"], "login": r["dono_login"]},
        "renovado_por": r["renovado_por"],
    }


def _validar_restricao(restricao: dict | None) -> dict:
    if not restricao:
        return {}
    extras = set(restricao) - {"referer", "ip"}
    if extras:
        raise ErroAPI(422, "restricao_invalida", "restrição aceita só as chaves referer e ip", sorted(extras))
    saida = {}
    for chave, lista in restricao.items():
        if not isinstance(lista, list) or len(lista) > limites.RESTRICAO_MAX:
            raise ErroAPI(422, "restricao_invalida", f"{chave}: no máximo {limites.RESTRICAO_MAX} entradas")
        limpa = []
        for item in lista:
            item = (item or "").strip()
            if not item:
                continue
            if chave == "ip":
                try:
                    ipaddress.ip_network(item, strict=False)
                except ValueError as e:
                    raise ErroAPI(422, "restricao_invalida", f"ip inválido: {item}") from e
            else:
                u = urlsplit(item)
                if u.scheme not in ("http", "https") or not u.hostname or u.path not in ("", "/"):
                    raise ErroAPI(
                        422, "restricao_invalida", f"referer precisa ser uma origem (esquema://host[:porta]): {item}"
                    )
            limpa.append(item)
        if limpa:
            saida[chave] = limpa
    return saida


def _validade(dias: int | None, auth: Auth) -> int:
    if dias is None:
        return auth.politica.token_padrao_dias
    if dias == 0:
        if settings.producao:
            raise ErroAPI(400, "validade_invalida", "validade_dias precisa ser pelo menos 1")
        return 0  # dev: token já expirado, para o teste do 401 token_expirado
    if dias > auth.politica.token_max_dias:
        raise ErroAPI(
            400,
            "validade_acima_do_maximo",
            f"validade máxima é {auth.politica.token_max_dias} dias",
            {"maximo_dias": auth.politica.token_max_dias},
        )
    return dias


def _carregar(cur, auth: Auth, token_id: int) -> dict:
    cur.execute(SQL_TOKEN + " WHERE k.id = %s", (token_id,))
    r = cur.fetchone()
    if r is None or (r["usuario_id"] != auth.usuario_id and not auth.tem("tokens.gerir_todos")):
        raise ErroAPI(404, "token_inexistente", "token inexistente")
    return r


def _inserir(cur, auth: Auth, nome: str, escopos: list[str], restricao: dict, dias: int) -> tuple[dict, str]:
    valor = "plat_" + secrets.token_urlsafe(32)
    cur.execute(
        """
        INSERT INTO plat.token_servico(tenant_id, usuario_id, nome, token_hash, prefixo, escopos, restricao, expira_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now() + make_interval(days => %s))
        RETURNING id, prefixo, escopos, expira_em""",
        (
            auth.tenant_id,
            auth.usuario_id,
            nome,
            sha256_hex(valor),
            valor[:12],
            escopos,
            __import__("json").dumps(restricao),
            dias,
        ),
    )
    return cur.fetchone(), valor


@router.get("", response_model=list[Token], openapi_extra={"x-auth": "S", "x-privilegio": "tokens.gerar"})
def listar(todos: int = 0, auth: Auth = autenticado("tokens.gerar", so_sessao=True)):
    if todos == 1 and not auth.tem("tokens.gerir_todos"):
        raise ErroAPI(
            403,
            "sem_privilegio",
            "ver os tokens do inquilino exige tokens.gerir_todos",
            {"exigido": "tokens.gerir_todos"},
        )
    with db.db(auth.contexto()) as cur:
        if todos == 1:
            cur.execute(SQL_TOKEN + " ORDER BY k.criado_em DESC")
        else:
            cur.execute(SQL_TOKEN + " WHERE k.usuario_id = %s ORDER BY k.criado_em DESC", (auth.usuario_id,))
        return [_json(r) for r in cur.fetchall()]


@router.post(
    "",
    response_model=TokenCriado,
    response_model_exclude_unset=True,
    status_code=201,
    openapi_extra={"x-auth": "S", "x-privilegio": "tokens.gerar"},
)
def criar(corpo: TokenCriar, request: Request, auth: Auth = autenticado("tokens.gerar", so_sessao=True)):
    ruins = esc.invalidos(corpo.escopos)
    if ruins:
        raise ErroAPI(422, "escopo_invalido", "escopo fora do vocabulário", ruins)
    # --- catálogo (L0-03): escopo com <uuid> exige item existente e legível pelo dono do token
    sem_item = esc.uuids_inexistentes(auth, corpo.escopos)
    if sem_item:
        raise ErroAPI(422, "escopo_item_inexistente", "item do escopo inexistente ou sem acesso", {"escopos": sem_item})
    if "admin:inquilino" in corpo.escopos and auth.perfil != "admin":
        raise ErroAPI(422, "escopo_fora_do_teto", "admin:inquilino só para dono com perfil admin")
    restricao = _validar_restricao(corpo.restricao)
    dias = _validade(corpo.validade_dias, auth)
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute(
                "SELECT count(*) AS n FROM plat.token_servico WHERE usuario_id = %s AND revogado_em IS NULL "
                "AND (expira_em IS NULL OR expira_em > now())",
                (auth.usuario_id,),
            )
            if cur.fetchone()["n"] >= limites.TOKENS_POR_USUARIO:
                raise ErroAPI(422, "limite_tokens", f"no máximo {limites.TOKENS_POR_USUARIO} tokens ativos por usuário")
            r, valor = _inserir(cur, auth, corpo.nome.strip(), sorted(set(corpo.escopos)), restricao, dias)
            registrar_evento(
                cur,
                request,
                "tokens/criar",
                "token",
                r["id"],
                {"nome": corpo.nome.strip(), "escopos": sorted(set(corpo.escopos)), "validade_dias": dias},
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {
        "token": valor,
        "id": r["id"],
        "prefixo": r["prefixo"],
        "escopos": list(r["escopos"]),
        "expira_em": iso(r["expira_em"]),
    }


@router.get(
    "/{id}", response_model=Token, openapi_extra={"x-auth": "S", "x-privilegio": "token:dono|tokens.gerir_todos"}
)
def ver(id: int, auth: Auth = autenticado("tokens.gerar", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        cur.execute(
            "SELECT count(*) AS n, (array_agg(status ORDER BY em DESC))[1] AS ultimo FROM plat.log_acesso "
            "WHERE token_id = %s AND em > now() - interval '30 days'",
            (id,),
        )
        a = cur.fetchone()
    return {**_json(r), "acessos_30d": a["n"], "ultimo_status": a["ultimo"]}


@router.post(
    "/{id}/renovar",
    response_model=TokenCriado,
    status_code=201,
    openapi_extra={"x-auth": "S", "x-privilegio": "token:dono"},
)
def renovar(id: int, request: Request, auth: Auth = autenticado("tokens.gerar", so_sessao=True)):
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, auth, id)
            if r["usuario_id"] != auth.usuario_id:
                raise ErroAPI(403, "so_dono_renova", "só o dono renova o token")
            if r["revogado_em"] is not None:
                raise ErroAPI(409, "token_revogado", f"token revogado em {iso(r['revogado_em'])}")
            cur.execute(
                "SELECT greatest(ceil(extract(epoch FROM (expira_em - criado_em)) / 86400)::int, 1) AS dias "
                "FROM plat.token_servico WHERE id = %s",
                (id,),
            )
            dias = min(cur.fetchone()["dias"], auth.politica.token_max_dias)
            novo, valor = _inserir(cur, auth, r["nome"], list(r["escopos"] or []), r["restricao"] or {}, dias)
            cur.execute(
                "UPDATE plat.token_servico SET expira_em = least(expira_em, now() + make_interval(hours => %s)), "
                "renovado_por = %s WHERE id = %s RETURNING expira_em",
                (limites.TOKEN_ROTACAO_HORAS, novo["id"], id),
            )
            antigo = cur.fetchone()["expira_em"]
            registrar_evento(cur, request, "tokens/renovar", "token", id, {"novo": novo["id"]})
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {
        "token": valor,
        "id": novo["id"],
        "prefixo": novo["prefixo"],
        "escopos": list(novo["escopos"]),
        "expira_em": iso(novo["expira_em"]),
        "antigo_expira_em": iso(antigo),
    }


@router.delete(
    "/{id}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S", "x-privilegio": "token:dono|tokens.gerir_todos"},
)
def revogar(id: int, request: Request, auth: Auth = autenticado("tokens.gerar", so_sessao=True)):
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, id)
        if r["revogado_em"] is None:
            cur.execute("UPDATE plat.token_servico SET revogado_em = now() WHERE id = %s", (id,))
            registrar_evento(cur, request, "tokens/revogar", "token", id, {"dono": r["usuario_id"]})
    return Response(status_code=204)


@router.get(
    "/{id}/log", response_model=Pagina, openapi_extra={"x-auth": "S", "x-privilegio": "token:dono|tokens.gerir_todos"}
)
def log_do_token(
    id: int,
    desde: str | None = None,
    ate: str | None = None,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado("tokens.gerar", so_sessao=True),
):
    from app.auth.rotas_log import consultar_log

    with db.db(auth.contexto()) as cur:
        _carregar(cur, auth, id)
        lim, desl = paginacao(limite, deslocamento, limites.LOG_LIMITE_MAX)
        return consultar_log(cur, token_id=id, desde=desde, ate=ate, limite=lim, deslocamento=desl)
