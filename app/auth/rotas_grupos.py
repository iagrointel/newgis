"""Grupos (ADR 0002 seção 4): UUID, papéis dono/gerente/membro, entrada convite/pedido/livre, marcações
atualizacao_compartilhada/administrativo/protegido. A visibilidade é RLS (p_grupo_ler); as regras de papel
vivem aqui; a coerência dono ↔ grupo_membro é gatilho."""

import uuid

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db, limites
from app.auth.comum import erro_do_banco, paginacao, registrar_evento
from app.auth.modelos import ConviteEntrada, Estado, Grupo, GrupoCriar, GrupoEditar, Membro, Pagina, PapelMembroEntrada
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI

router = APIRouter(prefix="/api/grupos", tags=["grupos"])
SQL_GRUPO = """
SELECT g.*, d.nome AS dono_nome, d.login AS dono_login,
       (SELECT count(*) FROM plat.grupo_membro x WHERE x.grupo_id = g.id AND x.estado = 'ativo') AS membros,
       m.papel AS meu_papel, m.estado AS meu_estado
FROM plat.grupo g JOIN plat.usuario d ON d.id = g.dono_id
LEFT JOIN plat.grupo_membro m ON m.grupo_id = g.id AND m.usuario_id = %s
"""


def _json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "resumo": r["resumo"],
        "tags": list(r["tags"] or []),
        "visibilidade": r["visibilidade"],
        "entrada": r["entrada"],
        "contribuicao": r["contribuicao"],
        "atualizacao_compartilhada": r["atualizacao_compartilhada"],
        "administrativo": r["administrativo"],
        "protegido": r["protegido"],
        "dono": {"id": r["dono_id"], "nome": r["dono_nome"], "login": r["dono_login"]},
        "membros": r["membros"],
        "meu_papel": r["meu_papel"],
        "meu_estado": r["meu_estado"],
        "criado_em": iso(r["criado_em"]),
    }


def _carregar(cur, auth: Auth, grupo_id: str) -> dict:
    cur.execute(SQL_GRUPO + " WHERE g.id = %s::uuid", (auth.usuario_id, grupo_id))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "grupo_inexistente", "grupo inexistente")
    return r


def _uuid_ok(valor: str) -> str:
    import uuid

    try:
        return str(uuid.UUID(valor))
    except ValueError as e:
        raise ErroAPI(404, "grupo_inexistente", "grupo inexistente") from e


def _gere(r: dict, auth: Auth) -> bool:
    return auth.tem("grupos.gerir_todos") or (r["meu_estado"] == "ativo" and r["meu_papel"] in ("dono", "gerente"))


def _dono(r: dict, auth: Auth) -> bool:
    return auth.tem("grupos.gerir_todos") or (r["meu_estado"] == "ativo" and r["meu_papel"] == "dono")


def _limite_grupos(cur, usuario_id: int) -> None:
    cur.execute("SELECT count(*) AS n FROM plat.grupo_membro WHERE usuario_id = %s", (usuario_id,))
    if cur.fetchone()["n"] >= limites.GRUPOS_POR_USUARIO:
        raise ErroAPI(422, "limite_grupos", f"no máximo {limites.GRUPOS_POR_USUARIO} grupos por usuário")


@router.get("", response_model=Pagina, openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def listar(
    meus: int = 0,
    q: str | None = None,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(),
):
    lim, desl = paginacao(limite, deslocamento)
    condicoes, params = ["true"], [auth.usuario_id]
    if meus == 1:
        condicoes.append("m.usuario_id IS NOT NULL")
    if q:
        condicoes.append("(g.nome ILIKE %s OR coalesce(g.resumo, '') ILIKE %s)")
        params += [f"%{q}%"] * 2
    onde = " WHERE " + " AND ".join(condicoes)
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) FROM (" + SQL_GRUPO + onde + ") s", params)
        total = cur.fetchone()["count"]
        cur.execute(SQL_GRUPO + onde + " ORDER BY g.nome LIMIT %s OFFSET %s", params + [lim, desl])
        return {"total": total, "itens": [_json(r) for r in cur.fetchall()]}


@router.post("", response_model=Grupo, status_code=201, openapi_extra={"x-auth": "S/T", "x-privilegio": "grupos.criar"})
def criar(corpo: GrupoCriar, request: Request, auth: Auth = autenticado("grupos.criar")):
    if corpo.atualizacao_compartilhada:
        if not auth.tem("grupos.atualizacao_compartilhada"):
            raise ErroAPI(
                403,
                "sem_privilegio",
                "exige grupos.atualizacao_compartilhada",
                {"exigido": "grupos.atualizacao_compartilhada"},
            )
        if corpo.entrada not in ("convite", "pedido"):
            raise ErroAPI(
                422,
                "atualizacao_exige_convite_ou_pedido",
                "grupo com atualização compartilhada exige entrada por convite ou pedido",
            )
    if corpo.administrativo and not auth.tem("grupos.administrativo"):
        raise ErroAPI(403, "sem_privilegio", "exige grupos.administrativo", {"exigido": "grupos.administrativo"})
    try:
        with db.db(auth.contexto()) as cur:
            _limite_grupos(cur, auth.usuario_id)
            # sem RETURNING: a política de SELECT só enxerga o grupo depois que o gatilho AFTER insere o membro dono
            gid = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO plat.grupo(id, tenant_id, nome, resumo, tags, visibilidade, entrada, contribuicao,
                                       atualizacao_compartilhada, administrativo, protegido, dono_id)
                VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    gid,
                    auth.tenant_id,
                    corpo.nome.strip(),
                    corpo.resumo,
                    corpo.tags,
                    corpo.visibilidade,
                    corpo.entrada,
                    corpo.contribuicao,
                    corpo.atualizacao_compartilhada,
                    corpo.administrativo,
                    corpo.protegido,
                    auth.usuario_id,
                ),
            )
            registrar_evento(cur, request, "grupos/criar", "grupo", gid, {"nome": corpo.nome.strip()})
            return _json(_carregar(cur, auth, gid))
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "nome_existente", "já existe um grupo com esse nome") from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.get("/{id}", response_model=Grupo, openapi_extra={"x-auth": "S/T", "x-privilegio": "rls:visibilidade"})
def ver(id: str, auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        return _json(_carregar(cur, auth, _uuid_ok(id)))


@router.put(
    "/{id}",
    response_model=Grupo,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:dono|gerente|grupos.gerir_todos"},
)
def editar(id: str, corpo: GrupoEditar, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    campos = corpo.model_dump(exclude_unset=True)
    if not campos:
        raise ErroAPI(422, "validacao", "nada a alterar")
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, auth, gid)
            if not _gere(r, auth):
                raise ErroAPI(403, "sem_permissao_no_grupo", "só dono ou gerente edita o grupo")
            if (
                "atualizacao_compartilhada" in campos
                and campos["atualizacao_compartilhada"] != r["atualizacao_compartilhada"]
            ):
                raise ErroAPI(409, "atualizacao_so_na_criacao", "atualização compartilhada só se define na criação")
            campos.pop("atualizacao_compartilhada", None)
            if any(k in campos for k in ("dono_id", "administrativo")) and not _dono(r, auth):
                raise ErroAPI(403, "so_dono", "só o dono transfere o grupo ou muda a marcação administrativa")
            if campos.get("administrativo") and not auth.tem("grupos.administrativo"):
                raise ErroAPI(
                    403, "sem_privilegio", "exige grupos.administrativo", {"exigido": "grupos.administrativo"}
                )
            entrada = campos.get("entrada", r["entrada"])
            if r["atualizacao_compartilhada"] and entrada not in ("convite", "pedido"):
                raise ErroAPI(
                    422,
                    "atualizacao_exige_convite_ou_pedido",
                    "grupo com atualização compartilhada exige entrada por convite ou pedido",
                )
            novo_dono = campos.get("dono_id")
            if novo_dono is not None and novo_dono != r["dono_id"]:
                cur.execute(
                    "SELECT 1 FROM plat.grupo_membro WHERE grupo_id = %s AND usuario_id = %s AND estado = 'ativo'",
                    (gid, novo_dono),
                )
                if cur.fetchone() is None:
                    raise ErroAPI(422, "novo_dono_nao_membro", "o novo dono precisa ser membro ativo do grupo")
                if r["atualizacao_compartilhada"]:
                    cur.execute(
                        "SELECT 'grupos.atualizacao_compartilhada' = ANY(plat.privilegios_de(%s)) AS ok", (novo_dono,)
                    )
                    if not cur.fetchone()["ok"]:
                        raise ErroAPI(
                            422,
                            "novo_dono_sem_privilegio",
                            "o novo dono precisa do privilégio grupos.atualizacao_compartilhada",
                        )
            cur.execute(
                """
                UPDATE plat.grupo SET nome = %s, resumo = %s, tags = %s, visibilidade = %s, entrada = %s,
                       contribuicao = %s,
                       administrativo = %s, protegido = %s, dono_id = %s WHERE id = %s""",
                (
                    campos.get("nome", r["nome"]).strip(),
                    campos.get("resumo", r["resumo"]),
                    campos.get("tags", list(r["tags"] or [])),
                    campos.get("visibilidade", r["visibilidade"]),
                    entrada,
                    campos.get("contribuicao", r["contribuicao"]),
                    campos.get("administrativo", r["administrativo"]),
                    campos.get("protegido", r["protegido"]),
                    novo_dono if novo_dono is not None else r["dono_id"],
                    gid,
                ),
            )
            if novo_dono is not None and novo_dono != r["dono_id"]:
                registrar_evento(
                    cur, request, "grupos/transferir", "grupo", gid, {"de": r["dono_id"], "para": novo_dono}
                )
            outros = sorted(k for k in campos if k != "dono_id")
            if outros:
                registrar_evento(cur, request, "grupos/atualizar", "grupo", gid, {"campos": outros})
            return _json(_carregar(cur, auth, gid))
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "nome_existente", "já existe um grupo com esse nome") from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.delete(
    "/{id}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:dono|grupos.gerir_todos"},
)
def apagar(id: str, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, auth, gid)
            if not _dono(r, auth):
                raise ErroAPI(403, "so_dono", "só o dono apaga o grupo")
            if r["protegido"]:
                raise ErroAPI(409, "grupo_protegido", "grupo protegido contra remoção; desligue a proteção antes")
            registrar_evento(cur, request, "grupos/apagar", "grupo", gid, {"nome": r["nome"]})
            cur.execute("DELETE FROM plat.grupo WHERE id = %s", (gid,))
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)


@router.get(
    "/{id}/membros",
    response_model=list[Membro],
    openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:membro|grupos.gerir_todos"},
)
def membros(id: str, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, gid)
        if not (auth.tem("grupos.gerir_todos") or r["meu_estado"] == "ativo"):
            raise ErroAPI(404, "grupo_inexistente", "grupo inexistente")
        cur.execute(
            """
            SELECT m.papel, m.estado, m.criado_em, u.id, u.nome, u.login FROM plat.grupo_membro m
            JOIN plat.usuario u ON u.id = m.usuario_id WHERE m.grupo_id = %s
            ORDER BY CASE m.papel WHEN 'dono' THEN 0 WHEN 'gerente' THEN 1 ELSE 2 END, u.nome""",
            (gid,),
        )
        return [
            {
                "usuario": {"id": x["id"], "nome": x["nome"], "login": x["login"]},
                "papel": x["papel"],
                "estado": x["estado"],
                "criado_em": iso(x["criado_em"]),
            }
            for x in cur.fetchall()
        ]


@router.post(
    "/{id}/membros",
    response_model=Estado,
    status_code=201,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:dono|gerente"},
)
def convidar(id: str, corpo: ConviteEntrada, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, auth, gid)
            if not _gere(r, auth):
                raise ErroAPI(403, "sem_permissao_no_grupo", "só dono ou gerente convida")
            cur.execute("SELECT id FROM plat.usuario WHERE id = %s AND ativo", (corpo.usuario_id,))
            if cur.fetchone() is None:
                raise ErroAPI(404, "usuario_inexistente", "usuário inexistente")
            cur.execute(
                "SELECT estado FROM plat.grupo_membro WHERE grupo_id = %s AND usuario_id = %s", (gid, corpo.usuario_id)
            )
            if cur.fetchone() is not None:
                raise ErroAPI(409, "ja_membro", "o usuário já é membro, convidado ou pediu entrada")
            _limite_grupos(cur, corpo.usuario_id)
            cur.execute(
                "INSERT INTO plat.grupo_membro(grupo_id, tenant_id, usuario_id, papel, estado, convidado_por) "
                "VALUES (%s, %s, %s, %s, 'convidado', %s)",
                (gid, auth.tenant_id, corpo.usuario_id, corpo.papel, auth.usuario_id),
            )
            registrar_evento(
                cur, request, "grupos/convidar", "usuario", corpo.usuario_id, {"grupo": gid, "papel": corpo.papel}
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {"estado": "convidado"}


@router.post("/{id}/entrar", response_model=Estado, openapi_extra={"x-auth": "S/T", "x-privilegio": "grupos.entrar"})
def entrar(id: str, request: Request, resposta: Response, auth: Auth = autenticado("grupos.entrar")):
    gid = _uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, auth, gid)
            if r["meu_estado"] is not None:
                raise ErroAPI(409, "ja_membro", "você já é membro, foi convidado ou já pediu entrada")
            if r["entrada"] == "convite":
                raise ErroAPI(403, "entrada_por_convite", "este grupo só recebe membros por convite")
            _limite_grupos(cur, auth.usuario_id)
            estado = "ativo" if r["entrada"] == "livre" else "pedido"
            cur.execute(
                "INSERT INTO plat.grupo_membro(grupo_id, tenant_id, usuario_id, papel, estado) "
                "VALUES (%s, %s, %s, 'membro', %s)",
                (gid, auth.tenant_id, auth.usuario_id, estado),
            )
            registrar_evento(cur, request, "grupos/entrar" if estado == "ativo" else "grupos/pedir", "grupo", gid)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    resposta.status_code = 200 if estado == "ativo" else 202
    return {"estado": estado}


@router.post("/{id}/aceitar", response_model=Estado, openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:convidado"})
def aceitar(id: str, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.grupo_membro SET estado = 'ativo' "
            "WHERE grupo_id = %s AND usuario_id = %s AND estado = 'convidado' "
            "RETURNING papel",
            (gid, auth.usuario_id),
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "sem_convite", "não há convite pendente para este grupo")
        registrar_evento(cur, request, "grupos/entrar", "grupo", gid, {"por": "convite"})
    return {"estado": "ativo"}


@router.post(
    "/{id}/recusar",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:convidado"},
)
def recusar(id: str, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "grupos/recusar", "grupo", gid)
        cur.execute(
            "DELETE FROM plat.grupo_membro WHERE grupo_id = %s AND usuario_id = %s AND estado = 'convidado' "
            "RETURNING papel",
            (gid, auth.usuario_id),
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "sem_convite", "não há convite pendente para este grupo")
    return Response(status_code=204)


@router.post(
    "/{id}/membros/{uid}/aprovar",
    response_model=Estado,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:dono|gerente"},
)
def aprovar(id: str, uid: int, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, auth, gid)
        if not _gere(r, auth):
            raise ErroAPI(403, "sem_permissao_no_grupo", "só dono ou gerente aprova pedidos")
        cur.execute(
            "UPDATE plat.grupo_membro SET estado = 'ativo' "
            "WHERE grupo_id = %s AND usuario_id = %s AND estado = 'pedido' "
            "RETURNING papel",
            (gid, uid),
        )
        if cur.fetchone() is None:
            raise ErroAPI(404, "sem_pedido", "não há pedido pendente desse usuário")
        registrar_evento(cur, request, "grupos/aprovar", "usuario", uid, {"grupo": gid})
    return {"estado": "ativo"}


@router.put(
    "/{id}/membros/{uid}", response_model=Estado, openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:dono|gerente"}
)
def papel_membro(id: str, uid: int, corpo: PapelMembroEntrada, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, auth, gid)
            if not _gere(r, auth):
                raise ErroAPI(403, "sem_permissao_no_grupo", "só dono ou gerente muda papel de membro")
            cur.execute(
                "SELECT papel, estado FROM plat.grupo_membro WHERE grupo_id = %s AND usuario_id = %s", (gid, uid)
            )
            m = cur.fetchone()
            if m is None:
                raise ErroAPI(404, "membro_inexistente", "usuário não é membro do grupo")
            if m["papel"] == "dono":
                raise ErroAPI(409, "papel_dono_via_grupo", "o dono só muda por PUT /api/grupos/{id} com dono_id")
            cur.execute(
                "UPDATE plat.grupo_membro SET papel = %s WHERE grupo_id = %s AND usuario_id = %s",
                (corpo.papel, gid, uid),
            )
            registrar_evento(
                cur, request, "grupos/papel", "usuario", uid, {"grupo": gid, "antes": m["papel"], "depois": corpo.papel}
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {"estado": m["estado"]}


@router.delete(
    "/{id}/membros/{uid}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "grupo:proprio|dono|gerente"},
)
def remover(id: str, uid: int, request: Request, auth: Auth = autenticado()):
    gid = _uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            r = _carregar(cur, auth, gid)
            cur.execute(
                "SELECT papel, estado FROM plat.grupo_membro WHERE grupo_id = %s AND usuario_id = %s", (gid, uid)
            )
            m = cur.fetchone()
            if m is None:
                raise ErroAPI(404, "membro_inexistente", "usuário não é membro do grupo")
            if m["papel"] == "dono":
                raise ErroAPI(409, "dono_nao_sai", "o dono não sai do grupo; transfira o grupo antes")
            if uid == auth.usuario_id:
                if r["administrativo"] and not auth.tem("grupos.gerir_todos"):
                    raise ErroAPI(409, "grupo_administrativo", "grupo administrativo: o membro não sai")
                tipo = "grupos/sair"
            else:
                if not _gere(r, auth):
                    raise ErroAPI(403, "sem_permissao_no_grupo", "só dono ou gerente remove membros")
                tipo = "grupos/remover"
            cur.execute("DELETE FROM plat.grupo_membro WHERE grupo_id = %s AND usuario_id = %s", (gid, uid))
            registrar_evento(
                cur, request, tipo, "usuario", uid, {"grupo": gid, "papel": m["papel"], "estado": m["estado"]}
            )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)
