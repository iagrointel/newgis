"""Pastas hierárquicas por inquilino (ADR 0004 seção 8.1): ≤ 5 níveis, nome único entre irmãs, visíveis a todos do
inquilino; contagem = itens que o ator lê; ciclo, profundidade e pasta cheia recusados pelo banco."""

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo import comum
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import Pasta, PastaArvore, PastaEditar, PastaEntrada
from app.erros import ErroAPI

router = APIRouter(prefix="/api/pastas", tags=["pastas"])
SQL_PASTA = """
SELECT p.*, p.ancestrais::text[] AS ancestrais, u.login AS dono_login, u.nome AS dono_nome,
       (SELECT count(*) FROM plat.item i WHERE i.pasta_id = p.id AND i.apagado_em IS NULL) AS itens_visiveis
FROM plat.pasta p JOIN plat.usuario u ON u.id = p.dono_id
"""


def _json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "pai_id": str(r["pai_id"]) if r["pai_id"] else None,
        "profundidade": r["profundidade"],
        "ancestrais": [str(a) for a in (r["ancestrais"] or [])],
        "itens_visiveis": r["itens_visiveis"],
        "dono": {"id": r["dono_id"], "login": r["dono_login"], "nome": r["dono_nome"]},
        "criado_em": iso(r["criado_em"]),
    }


def _carregar(cur, pid: str) -> dict:
    cur.execute(SQL_PASTA + " WHERE p.id = %s::uuid", (pid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "pasta_inexistente", "pasta inexistente")
    return r


def _pode(r: dict, auth: Auth) -> None:
    if r["dono_id"] != auth.usuario_id and not auth.tem("conteudo.editar_tudo"):
        raise ErroAPI(403, "sem_permissao", "só o dono da pasta ou conteudo.editar_tudo")


@router.get("", response_model=list[Pasta], openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def listar(pai_id: str | None = None, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        if pai_id:
            cur.execute(
                SQL_PASTA + " WHERE p.pai_id = %s::uuid ORDER BY lower(p.nome)",
                (uuid_ok(pai_id, "pasta_inexistente", "pasta inexistente"),),
            )
        else:
            cur.execute(SQL_PASTA + " WHERE p.pai_id IS NULL ORDER BY lower(p.nome)")
        return [_json(r) for r in cur.fetchall()]


@router.get(
    "/arvore", response_model=list[PastaArvore], openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
)
def arvore(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute(SQL_PASTA + " ORDER BY p.profundidade, lower(p.nome)")
        nos = {str(r["id"]): {**_json(r), "filhas": []} for r in cur.fetchall()}
    raiz = []
    for no in nos.values():
        if no["pai_id"] and no["pai_id"] in nos:
            nos[no["pai_id"]]["filhas"].append(no)
        else:
            raiz.append(no)
    return raiz


@router.post(
    "", response_model=Pasta, status_code=201, openapi_extra={"x-auth": "S/T", "x-privilegio": "conteudo.criar"}
)
def criar(corpo: PastaEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    nome = " ".join(corpo.nome.split())
    pai = uuid_ok(corpo.pai_id, "pasta_inexistente", "pasta inexistente") if corpo.pai_id else None
    try:
        with db.db(auth.contexto()) as cur:
            if pai:
                _carregar(cur, pai)
            cur.execute(
                "INSERT INTO plat.pasta(tenant_id, pai_id, nome, dono_id) VALUES (%s, %s::uuid, %s, %s) RETURNING id",
                (auth.tenant_id, pai, nome, auth.usuario_id),
            )
            pid = str(cur.fetchone()["id"])
            registrar_evento(cur, request, "pastas/criar", "pasta", pid, {"nome": nome, "pai_id": pai})
            return _json(_carregar(cur, pid))
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "nome_existente", "já existe uma pasta com esse nome no mesmo lugar") from e
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.put(
    "/{id}",
    response_model=Pasta,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"},
)
def editar(id: str, corpo: PastaEditar, request: Request, auth: Auth = autenticado()):
    pid = uuid_ok(id, "pasta_inexistente", "pasta inexistente")
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, pid)
            _pode(r, auth)
            if corpo.nome is not None:
                nome = " ".join(corpo.nome.split())
                if nome != r["nome"]:
                    cur.execute("UPDATE plat.pasta SET nome = %s WHERE id = %s::uuid", (nome, pid))
                    registrar_evento(cur, request, "pastas/renomear", "pasta", pid, {"de": r["nome"], "para": nome})
            if corpo.pai_id is not None or corpo.para_raiz:
                novo_pai = None if corpo.para_raiz else uuid_ok(corpo.pai_id, "pasta_inexistente", "pasta inexistente")
                if novo_pai:
                    _carregar(cur, novo_pai)
                if novo_pai != (str(r["pai_id"]) if r["pai_id"] else None):
                    cur.execute("UPDATE plat.pasta SET pai_id = %s::uuid WHERE id = %s::uuid", (novo_pai, pid))
                    registrar_evento(
                        cur,
                        request,
                        "pastas/mover",
                        "pasta",
                        pid,
                        {"de": str(r["pai_id"]) if r["pai_id"] else None, "para": novo_pai},
                    )
            return _json(_carregar(cur, pid))
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "nome_existente", "já existe uma pasta com esse nome no mesmo lugar") from e
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.delete(
    "/{id}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"},
)
def apagar(id: str, request: Request, auth: Auth = autenticado()):
    pid = uuid_ok(id, "pasta_inexistente", "pasta inexistente")
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, pid)
            _pode(r, auth)
            cur.execute(
                "SELECT (SELECT count(*) FROM plat.item WHERE pasta_id = %s::uuid) AS itens, "
                "(SELECT count(*) FROM plat.pasta WHERE pai_id = %s::uuid) AS pastas",
                (pid, pid),
            )
            n = cur.fetchone()
            if n["itens"] or n["pastas"]:
                raise ErroAPI(
                    409,
                    "pasta_nao_vazia",
                    "a pasta tem itens ou subpastas; mova-os antes",
                    {"itens": n["itens"], "pastas": n["pastas"]},
                )
            registrar_evento(cur, request, "pastas/apagar", "pasta", pid, {"nome": r["nome"]})
            cur.execute("DELETE FROM plat.pasta WHERE id = %s::uuid", (pid,))
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    return Response(status_code=204)
