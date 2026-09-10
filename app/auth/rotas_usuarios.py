"""Usuários do inquilino, privilégios e papéis personalizados (ADR 0002 seções 2.3, 3, 6.3, 7.3, 14). Regras que
o banco também garante por gatilho (último admin, superadmin só na plataforma) chegam aqui como 409/422."""

import secrets

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db, limites, senha
from app.auth import privilegios as priv
from app.auth.comum import (
    SQL_USUARIO,
    carregar_usuario,
    erro_do_banco,
    paginacao,
    registrar_evento,
    so_admin_sobre_admin,
    usuario_json,
    usuario_ou_404,
)
from app.auth.modelos import (
    LoteEntrada,
    LoteSaida,
    Pagina,
    Papeis,
    Papel,
    PapelEntrada,
    Privilegio,
    SenhaTemporaria,
    Usuario,
    UsuarioCriado,
    UsuarioCriar,
    UsuarioEditar,
)
from app.auth.politica import email_permitido
from app.auth.sessao import Auth, autenticado, iso
from app.erros import ErroAPI

router = APIRouter(prefix="/api", tags=["usuarios"])
ORDENS = {
    "login": "u.login",
    "nome": "u.nome",
    "ultimo_login": "u.ultimo_login DESC NULLS LAST",
    "criado_em": "u.criado_em DESC",
}


def _senha_temporaria() -> str:
    return secrets.token_urlsafe(limites.SENHA_TEMPORARIA_TAMANHO)[: limites.SENHA_TEMPORARIA_TAMANHO]


def _email_ok(email: str | None, auth: Auth) -> None:
    if email and not email_permitido(email, auth.politica):
        raise ErroAPI(
            422,
            "email_dominio",
            "e-mail fora dos domínios permitidos do inquilino",
            {"dominios": list(auth.politica.dominios_email)},
        )


def _papel_compativel(cur, papel_id: int | None, perfil: str) -> None:
    if papel_id is None:
        return
    cur.execute("SELECT perfil_minimo FROM plat.papel_personalizado WHERE id = %s", (papel_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "papel_inexistente", "papel inexistente")
    if priv.ORDEM_PERFIL[perfil] < priv.ORDEM_PERFIL[r["perfil_minimo"]]:
        raise ErroAPI(
            422,
            "papel_incompativel",
            f"o papel exige perfil {r['perfil_minimo']} ou maior",
            {"perfil_minimo": r["perfil_minimo"]},
        )


def _privilegios_concedidos(cur, perfil: str, papel_id: int | None) -> set[str]:
    """Privilégios efetivos que o alvo passa a ter com (perfil, papel_id).

    É a MESMA conta de `plat.privilegios_de` (migração 003, seção 12.10): teto do perfil interseção com o
    papel personalizado, que só restringe, nunca amplia. Lê do banco, não da lista em Python, para não haver
    duas verdades sobre o teto de cada perfil."""
    cur.execute(
        """
        SELECT pp.privilegio FROM plat.perfil_privilegio pp
         WHERE pp.perfil = %s
           AND (%s::int IS NULL
                OR EXISTS (SELECT 1 FROM plat.papel_privilegio x
                            WHERE x.papel_id = %s AND x.privilegio = pp.privilegio))""",
        (perfil, papel_id, papel_id),
    )
    return {r["privilegio"] for r in cur.fetchall()}


def _nao_conceder_alem_do_proprio(cur, auth: Auth, perfil: str, papel_id: int | None) -> None:
    """Ninguém concede privilégio que não tem (item L0-02-g-checagem-privilegio-papel-id).

    O papel personalizado é uma RESTRIÇÃO do teto do perfil, então um administrador restrito por um papel
    tinha, até aqui, dois caminhos de escalonamento: atribuir a outro (ou a si mesmo) um papel mais amplo,
    ou tirar o papel (papel_id nulo), o que devolve o teto inteiro do perfil. As rotas de papel já barravam
    isso na CRIAÇÃO do papel (`_validar_papel`); faltava barrar na ATRIBUIÇÃO. Vale para perfil e papel
    juntos, porque promover de editor para admin com papel nulo concede exatamente o mesmo conjunto."""
    # o teto do perfil `visualizador` é o PISO de todo membro (ver, entrar em grupo, gerar o próprio token…): não é
    # "concedido" por ninguém, e por isso não conta na sobra — sem isso um administrador restrito a
    # {membros.ver, membros.gerir} não conseguiria criar nem um visualizador (regra do L0-02-f, test_usuarios.py)
    piso = _privilegios_concedidos(cur, "visualizador", None)
    sobra = sorted(_privilegios_concedidos(cur, perfil, papel_id) - piso - set(auth.privilegios))
    if sobra:
        raise ErroAPI(403, "privilegio_proprio_insuficiente", "não se concede privilégio que não se tem", sobra)


def _grupos_do_dono(cur, usuario_id: int) -> list[dict]:
    cur.execute("SELECT id, nome FROM plat.grupo WHERE dono_id = %s ORDER BY nome", (usuario_id,))
    return [{"id": str(r["id"]), "nome": r["nome"]} for r in cur.fetchall()]


def _itens_do_dono(cur, usuario_id: int) -> list[dict]:
    """Itens do catálogo (mapas, camadas, pastas) que o usuário ainda possui — inclusive na lixeira, porque
    `plat.item.dono_id` é FK sem `ON DELETE`: sem esta checagem a exclusão cairia num `409 em_uso` genérico do
    banco (nome da constraint, não os títulos). Transferir é o item L0-03-j (`POST /api/itens/transferir`)."""
    cur.execute(
        "SELECT id, titulo FROM plat.item WHERE dono_id = %s ORDER BY titulo LIMIT 50",
        (usuario_id,),
    )
    return [{"id": str(r["id"]), "titulo": r["titulo"]} for r in cur.fetchall()]


def _editar(cur, auth: Auth, request: Request, alvo: dict, campos: dict) -> dict:
    """Aplica {nome, email, perfil, papel_id, ativo} a um usuário já carregado; levanta ErroAPI; devolve a linha."""
    if any(k in campos for k in ("nome", "email", "ativo")) and not auth.tem("membros.gerir"):
        raise ErroAPI(
            403, "sem_privilegio", "editar nome, e-mail ou estado exige membros.gerir", {"exigido": "membros.gerir"}
        )
    if any(k in campos for k in ("perfil", "papel_id")) and not auth.tem("membros.papel"):
        raise ErroAPI(403, "sem_privilegio", "mudar perfil ou papel exige membros.papel", {"exigido": "membros.papel"})
    novo_perfil = campos.get("perfil", alvo["perfil"])
    so_admin_sobre_admin(auth, alvo["perfil"], campos.get("perfil"), "so_admin_altera_admin")
    if "email" in campos:
        _email_ok(campos["email"], auth)
    if "perfil" in campos and priv.ORDEM_PERFIL[novo_perfil] < priv.ORDEM_PERFIL[alvo["perfil"]]:
        # regra da Esri (E12-members): rebaixar o tipo de usuário só se ele "não possui conteúdo nem grupos" —
        # a rota já checava grupos; achado do adversário do item L0-07-b: conteúdo (itens do catálogo) não era
        # checado, então um admin com mapas/camadas publicadas virava visualizador sem aviso, e o dono passava a
        # não poder mais editar/apagar o próprio material (perfil não alcança mais `conteudo.criar`).
        grupos = _grupos_do_dono(cur, alvo["id"])
        if grupos:
            raise ErroAPI(409, "possui_grupos", "rebaixar quem possui grupos: transfira os grupos antes", grupos)
        itens = _itens_do_dono(cur, alvo["id"])
        if itens:
            raise ErroAPI(
                409,
                "possui_itens",
                "rebaixar quem possui itens: transfira-os antes (POST /api/itens/transferir) ou apague-os",
                itens,
            )
    papel_id = campos["papel_id"] if "papel_id" in campos else alvo["papel_id"]
    if "perfil" in campos or "papel_id" in campos:
        _papel_compativel(cur, papel_id, novo_perfil)
        _nao_conceder_alem_do_proprio(cur, auth, novo_perfil, papel_id)
    cur.execute(
        """
        UPDATE plat.usuario SET nome = %s, email = %s, perfil = %s, papel_id = %s, ativo = %s WHERE id = %s""",
        (
            campos.get("nome", alvo["nome"]),
            campos["email"] if "email" in campos else alvo["email"],
            novo_perfil,
            papel_id,
            campos.get("ativo", alvo["ativo"]),
            alvo["id"],
        ),
    )
    if "ativo" in campos and campos["ativo"] != alvo["ativo"]:
        registrar_evento(
            cur,
            request,
            "usuarios/reabilitar" if campos["ativo"] else "usuarios/desabilitar",
            "usuario",
            alvo["id"],
            {"antes": alvo["ativo"], "depois": campos["ativo"]},
        )
        if not campos["ativo"]:
            cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, NULL)", (alvo["id"],))
    if ("perfil" in campos and campos["perfil"] != alvo["perfil"]) or (
        "papel_id" in campos and papel_id != alvo["papel_id"]
    ):
        registrar_evento(
            cur,
            request,
            "usuarios/papel",
            "usuario",
            alvo["id"],
            {
                "antes": {"perfil": alvo["perfil"], "papel_id": alvo["papel_id"]},
                "depois": {"perfil": novo_perfil, "papel_id": papel_id},
            },
        )
    if any(k in campos and campos[k] != alvo[k] for k in ("nome", "email")):
        registrar_evento(
            cur,
            request,
            "usuarios/atualizar",
            "usuario",
            alvo["id"],
            {"campos": [k for k in ("nome", "email") if k in campos]},
        )
    return usuario_ou_404(cur, alvo["id"])


# ---------------------------------------------------------------- privilégios e papéis
@router.get(
    "/privilegios", response_model=list[Privilegio], openapi_extra={"x-auth": "S/T", "x-privilegio": "vocabulario"}
)
def listar_privilegios(auth: Auth = autenticado(escopo_token=None)):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT nome, grupo, descricao, administrativo FROM plat.privilegio ORDER BY grupo, nome")
        return cur.fetchall()


def _papel_json(cur, r: dict) -> dict:
    cur.execute("SELECT privilegio FROM plat.papel_privilegio WHERE papel_id = %s ORDER BY 1", (r["id"],))
    privs = [x["privilegio"] for x in cur.fetchall()]
    cur.execute("SELECT count(*) AS n FROM plat.usuario WHERE papel_id = %s", (r["id"],))
    return {
        "id": r["id"],
        "nome": r["nome"],
        "descricao": r["descricao"],
        "perfil_minimo": r["perfil_minimo"],
        "privilegios": privs,
        "usuarios": cur.fetchone()["n"],
        "criado_em": iso(r["criado_em"]),
    }


def _validar_papel(cur, auth: Auth, corpo: PapelEntrada) -> tuple[set[str], str]:
    pedidos = set(corpo.privilegios)
    desconhecidos = sorted(pedidos - priv.NOMES)
    if desconhecidos:
        raise ErroAPI(422, "privilegio_desconhecido", "privilégio fora do vocabulário", desconhecidos)
    perfil_minimo = priv.perfil_minimo(pedidos)
    if perfil_minimo is None:
        raise ErroAPI(422, "privilegio_fora_do_teto", "nenhum perfil contém todos os privilégios", sorted(pedidos))
    sobra = sorted(pedidos - set(auth.privilegios))
    if sobra:
        raise ErroAPI(403, "privilegio_proprio_insuficiente", "não se concede privilégio que não se tem", sobra)
    return pedidos, perfil_minimo


@router.get("/papeis", response_model=Papeis, openapi_extra={"x-auth": "S/T", "x-privilegio": "vocabulario"})
def listar_papeis(auth: Auth = autenticado()):
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT perfil, array_agg(privilegio ORDER BY privilegio) AS privilegios FROM plat.perfil_privilegio "
            "GROUP BY perfil"
        )
        perfis = sorted(cur.fetchall(), key=lambda r: priv.ORDEM_PERFIL[r["perfil"]])
        cur.execute("SELECT * FROM plat.papel_personalizado ORDER BY nome")
        personalizados = [_papel_json(cur, r) for r in cur.fetchall()]
    return {
        "perfis": [{"perfil": r["perfil"], "privilegios": list(r["privilegios"])} for r in perfis],
        "personalizados": personalizados,
    }


@router.post(
    "/papeis", response_model=Papel, status_code=201, openapi_extra={"x-auth": "S/T", "x-privilegio": "papeis.gerir"}
)
def criar_papel(corpo: PapelEntrada, request: Request, auth: Auth = autenticado("papeis.gerir")):
    try:
        with db.db(auth.contexto()) as cur:
            pedidos, perfil_minimo = _validar_papel(cur, auth, corpo)
            cur.execute(
                "INSERT INTO plat.papel_personalizado(tenant_id, nome, descricao, perfil_minimo, criado_por) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING *",
                (auth.tenant_id, corpo.nome.strip(), corpo.descricao, perfil_minimo, auth.usuario_id),
            )
            r = cur.fetchone()
            cur.executemany(
                "INSERT INTO plat.papel_privilegio(papel_id, privilegio) VALUES (%s, %s)",
                [(r["id"], p) for p in sorted(pedidos)],
            )
            registrar_evento(
                cur, request, "papeis/criar", "papel", r["id"], {"nome": r["nome"], "privilegios": sorted(pedidos)}
            )
            return _papel_json(cur, r)
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "nome_existente", "já existe um papel com esse nome") from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.put("/papeis/{id}", response_model=Papel, openapi_extra={"x-auth": "S/T", "x-privilegio": "papeis.gerir"})
def editar_papel(id: int, corpo: PapelEntrada, request: Request, auth: Auth = autenticado("papeis.gerir")):
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT * FROM plat.papel_personalizado WHERE id = %s", (id,))
            r = cur.fetchone()
            if r is None:
                raise ErroAPI(404, "papel_inexistente", "papel inexistente")
            pedidos, perfil_minimo = _validar_papel(cur, auth, corpo)
            cur.execute(
                "SELECT count(*) AS n FROM plat.usuario WHERE papel_id = %s AND perfil <> 'admin' AND "
                "perfil <> ALL(%s)",
                (id, [p for p in priv.PERFIS if priv.ORDEM_PERFIL[p] >= priv.ORDEM_PERFIL[perfil_minimo]]),
            )
            n = cur.fetchone()["n"]
            if n:
                raise ErroAPI(
                    422,
                    "papel_incompativel",
                    f"{n} usuário(s) com perfil abaixo de {perfil_minimo} usam este papel",
                    {"usuarios": n, "perfil_minimo": perfil_minimo},
                )
            cur.execute(
                "UPDATE plat.papel_personalizado SET nome = %s, descricao = %s, perfil_minimo = %s WHERE id = %s "
                "RETURNING *",
                (corpo.nome.strip(), corpo.descricao, perfil_minimo, id),
            )
            r = cur.fetchone()
            cur.execute("DELETE FROM plat.papel_privilegio WHERE papel_id = %s", (id,))
            cur.executemany(
                "INSERT INTO plat.papel_privilegio(papel_id, privilegio) VALUES (%s, %s)",
                [(id, p) for p in sorted(pedidos)],
            )
            registrar_evento(
                cur, request, "papeis/atualizar", "papel", id, {"nome": r["nome"], "privilegios": sorted(pedidos)}
            )
            return _papel_json(cur, r)
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "nome_existente", "já existe um papel com esse nome") from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.delete(
    "/papeis/{id}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "papeis.gerir"},
)
def apagar_papel(id: int, request: Request, auth: Auth = autenticado("papeis.gerir")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT nome FROM plat.papel_personalizado WHERE id = %s", (id,))
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "papel_inexistente", "papel inexistente")
        cur.execute("SELECT count(*) AS n FROM plat.usuario WHERE papel_id = %s", (id,))
        n = cur.fetchone()["n"]
        if n:
            raise ErroAPI(409, "papel_em_uso", f"{n} usuário(s) usam este papel", {"usuarios": n})
        registrar_evento(cur, request, "papeis/apagar", "papel", id, {"nome": r["nome"]})
        cur.execute("DELETE FROM plat.papel_personalizado WHERE id = %s", (id,))
    return Response(status_code=204)


# ---------------------------------------------------------------- usuários
@router.get("/usuarios", response_model=Pagina, openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.ver"})
def listar_usuarios(
    perfil: str | None = None,
    ativo: bool | None = None,
    q: str | None = None,
    limite: int | None = None,
    deslocamento: int | None = None,
    ordenar: str = "login",
    auth: Auth = autenticado("membros.ver", superadmin_pode_ler=True),
):
    lim, desl = paginacao(limite, deslocamento)
    if ordenar not in ORDENS:
        raise ErroAPI(422, "validacao", f"ordenar aceita {', '.join(ORDENS)}", {"campo": "ordenar"})
    if perfil is not None and perfil not in priv.PERFIS:
        raise ErroAPI(422, "validacao", "perfil desconhecido", {"campo": "perfil"})
    condicoes, params = ["true"], []
    if perfil is not None:
        condicoes.append("u.perfil = %s")
        params.append(perfil)
    if ativo is not None:
        condicoes.append("u.ativo = %s")
        params.append(ativo)
    if q:
        condicoes.append("(u.login ILIKE %s OR u.nome ILIKE %s OR coalesce(u.email, '') ILIKE %s)")
        params += [f"%{q}%"] * 3
    onde = " WHERE " + " AND ".join(condicoes)
    completo = auth.tem("membros.ver_tudo")
    with db.db(auth.contexto_leitura(), somente_leitura=auth.leitura_inquilino is not None) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.usuario u" + onde, params)
        total = cur.fetchone()["n"]
        cur.execute(SQL_USUARIO + onde + f" ORDER BY {ORDENS[ordenar]} LIMIT %s OFFSET %s", params + [lim, desl])
        itens = [usuario_json(r, completo) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.post(
    "/usuarios",
    response_model=UsuarioCriado,
    status_code=201,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.gerir"},
)
def criar_usuario(corpo: UsuarioCriar, request: Request, auth: Auth = autenticado("membros.gerir")):
    if corpo.perfil == "admin" and auth.perfil != "admin":
        raise ErroAPI(403, "so_admin_cria_admin", "só um administrador cria outro administrador")
    # achado do adversário T3: só `membros.gerir` (sem `membros.papel`) bastava para criar um admin pleno, ou um
    # usuário com QUALQUER papel_id — igual à edição (_editar exige membros.papel para mexer em perfil/papel_id),
    # a criação tem de exigir o mesmo; "visualizador" sem papel é o piso que membros.gerir sozinho ainda cobre.
    if (corpo.perfil != "visualizador" or corpo.papel_id is not None) and not auth.tem("membros.papel"):
        raise ErroAPI(
            403,
            "sem_privilegio",
            "criar com perfil diferente de visualizador, ou com papel, exige membros.papel",
            {"exigido": "membros.papel"},
        )
    _email_ok(corpo.email, auth)
    temporaria = _senha_temporaria()
    try:
        with db.db(auth.contexto()) as cur:
            # cota de usuários do inquilino (item L0-07-a-configuracoes-org, tenant.config.cota_usuarios): checagem
            # simples, não atômica sob concorrência — a reserva à prova de corrida (SELECT ... FOR UPDATE, mesmo
            # padrão que o item de cota de armazenamento/uso exige) é responsabilidade do item L0-07-c-cotas-uso,
            # que cobre TODAS as cotas do inquilino junto; aqui a cota só deixa de ser um campo sem efeito.
            cur.execute(
                "SELECT plat.cota_usuarios(%s) AS cota, plat.usuarios_ativos(%s) AS ativos",
                (auth.tenant_id, auth.tenant_id),
            )
            cota = cur.fetchone()
            if cota["ativos"] >= cota["cota"]:
                raise ErroAPI(
                    413, "cota_usuarios", f"cota de usuários do inquilino esgotada ({cota['cota']})",
                    {"cota": cota["cota"]},
                )
            _papel_compativel(cur, corpo.papel_id, corpo.perfil)
            _nao_conceder_alem_do_proprio(cur, auth, corpo.perfil, corpo.papel_id)
            cur.execute(
                """
                INSERT INTO plat.usuario(tenant_id, login, nome, email, senha_hash, perfil, papel_id, trocar_senha)
                VALUES (%s, %s, %s, %s, %s, %s, %s, true) RETURNING id""",
                (
                    auth.tenant_id,
                    corpo.login.strip().lower(),
                    corpo.nome.strip(),
                    corpo.email,
                    senha.gerar_hash(temporaria),
                    corpo.perfil,
                    corpo.papel_id,
                ),
            )
            novo = cur.fetchone()["id"]
            registrar_evento(
                cur,
                request,
                "usuarios/criar",
                "usuario",
                novo,
                {"login": corpo.login.strip().lower(), "perfil": corpo.perfil, "papel_id": corpo.papel_id},
            )
            u = usuario_json(usuario_ou_404(cur, novo))
    except psycopg2.errors.UniqueViolation as e:
        raise ErroAPI(409, "login_existente", "já existe um usuário com esse login") from e
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return {"usuario": u, "senha_temporaria": temporaria}


@router.post(
    "/usuarios/lote",
    response_model=LoteSaida,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.gerir|membros.papel"},
)
def lote(corpo: LoteEntrada, request: Request, auth: Auth = autenticado()):
    if len(corpo.ids) > limites.LOTE_MAX:
        raise ErroAPI(422, "lote_acima_de_100", f"no máximo {limites.LOTE_MAX} usuários por lote")
    if corpo.acao == "perfil" and not corpo.perfil:
        raise ErroAPI(422, "validacao", "acao=perfil exige perfil", {"campo": "perfil"})
    if corpo.acao == "papel" and corpo.papel_id is None:
        raise ErroAPI(422, "validacao", "acao=papel exige papel_id", {"campo": "papel_id"})
    campos = {
        "perfil": {"perfil": corpo.perfil},
        "papel": {"papel_id": corpo.papel_id},
        "desabilitar": {"ativo": False},
        "reabilitar": {"ativo": True},
    }[corpo.acao]
    exigido = "membros.papel" if corpo.acao in ("perfil", "papel") else "membros.gerir"
    if not auth.tem(exigido):
        raise ErroAPI(403, "sem_privilegio", f"a ação exige {exigido}", {"exigido": exigido})
    alterados, recusados = 0, []
    with db.db(auth.contexto()) as cur:
        for uid in dict.fromkeys(corpo.ids):
            cur.execute("SAVEPOINT item")
            try:
                alvo = carregar_usuario(cur, uid)
                if alvo is None:
                    raise ErroAPI(404, "usuario_inexistente", "usuário inexistente")
                if alvo["id"] == auth.usuario_id and corpo.acao == "desabilitar":
                    raise ErroAPI(409, "proprio_usuario", "não se desabilita a própria conta")
                _editar(cur, auth, request, alvo, dict(campos))
                cur.execute("RELEASE SAVEPOINT item")
                alterados += 1
            except ErroAPI as e:
                cur.execute("ROLLBACK TO SAVEPOINT item")
                recusados.append({"id": uid, "erro": e.erro, "mensagem": e.mensagem})
            except psycopg2.Error as e:
                cur.execute("ROLLBACK TO SAVEPOINT item")
                erro = erro_do_banco(e)
                recusados.append({"id": uid, "erro": erro.erro, "mensagem": erro.mensagem})
    return {"alterados": alterados, "recusados": recusados}


@router.get(
    "/usuarios/{id}",
    response_model=Usuario,
    response_model_exclude_unset=True,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.ver"},
)
def ver_usuario(id: int, auth: Auth = autenticado("membros.ver")):
    with db.db(auth.contexto()) as cur:
        return usuario_json(usuario_ou_404(cur, id), auth.tem("membros.ver_tudo"))


@router.put(
    "/usuarios/{id}",
    response_model=Usuario,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.gerir|membros.papel"},
)
def editar_usuario(id: int, corpo: UsuarioEditar, request: Request, auth: Auth = autenticado()):
    campos = corpo.model_dump(exclude_unset=True)
    if not campos:
        raise ErroAPI(422, "validacao", "nada a alterar")
    if id == auth.usuario_id and campos.get("ativo") is False:
        raise ErroAPI(409, "proprio_usuario", "não se desabilita a própria conta")
    try:
        with db.db(auth.contexto()) as cur:
            alvo = usuario_ou_404(cur, id)
            return usuario_json(_editar(cur, auth, request, alvo, campos))
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


@router.post(
    "/usuarios/{id}/senha",
    response_model=SenhaTemporaria,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.gerir"},
)
def redefinir_senha(id: int, request: Request, auth: Auth = autenticado("membros.gerir")):
    temporaria = _senha_temporaria()
    with db.db(auth.contexto()) as cur:
        alvo = usuario_ou_404(cur, id)
        so_admin_sobre_admin(auth, alvo["perfil"], None, "so_admin_altera_admin")
        if alvo["origem"] != "local":
            raise ErroAPI(409, "login_externo", "conta federada não tem senha local")
        cur.execute(
            "UPDATE plat.usuario SET senha_hash = %s, trocar_senha = true, senha_alterada_em = now(), "
            "bloqueado_ate = NULL, falhas_login = 0, falhas_desde = NULL WHERE id = %s",
            (senha.gerar_hash(temporaria), id),
        )
        cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, NULL)", (id,))
        registrar_evento(cur, request, "usuarios/redefinir_senha", "usuario", id)
    return {"senha_temporaria": temporaria}


@router.post(
    "/usuarios/{id}/2fa/desativar",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.gerir"},
)
def desativar_2fa_de(id: int, request: Request, auth: Auth = autenticado("membros.gerir")):
    with db.db(auth.contexto()) as cur:
        alvo = usuario_ou_404(cur, id)
        so_admin_sobre_admin(auth, alvo["perfil"], None, "so_admin_altera_admin")
        cur.execute(
            "UPDATE plat.usuario SET totp_secret = NULL, totp_ativo = false, totp_ultimo_passo = NULL, "
            "codigos_recuperacao = NULL WHERE id = %s",
            (id,),
        )
        cur.execute("SELECT plat.sessoes_encerrar_usuario(%s, NULL)", (id,))
        registrar_evento(cur, request, "usuarios/2fa_desligar", "usuario", id, {"proprio": id == auth.usuario_id})
    return Response(status_code=204)


@router.post(
    "/usuarios/{id}/desbloquear",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.gerir"},
)
def desbloquear(id: int, request: Request, auth: Auth = autenticado("membros.gerir")):
    with db.db(auth.contexto()) as cur:
        usuario_ou_404(cur, id)
        cur.execute(
            "UPDATE plat.usuario SET bloqueado_ate = NULL, falhas_login = 0, falhas_desde = NULL WHERE id = %s", (id,)
        )
        registrar_evento(cur, request, "usuarios/desbloquear", "usuario", id)
    return Response(status_code=204)


@router.delete(
    "/usuarios/{id}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "membros.apagar"},
)
def apagar_usuario(id: int, request: Request, auth: Auth = autenticado("membros.apagar")):
    if id == auth.usuario_id:
        raise ErroAPI(409, "proprio_usuario", "não se apaga a própria conta")
    try:
        with db.db(auth.contexto()) as cur:
            alvo = usuario_ou_404(cur, id)
            so_admin_sobre_admin(auth, alvo["perfil"], None, "so_admin_apaga_admin")
            grupos = _grupos_do_dono(cur, id)
            if grupos:
                raise ErroAPI(409, "possui_grupos", "o usuário possui grupos; transfira-os antes", grupos)
            itens = _itens_do_dono(cur, id)
            if itens:
                raise ErroAPI(
                    409,
                    "possui_itens",
                    "o usuário possui itens; transfira-os antes (POST /api/itens/transferir) ou apague-os",
                    itens,
                )
            registrar_evento(
                cur, request, "usuarios/apagar", "usuario", id, {"login": alvo["login"], "perfil": alvo["perfil"]}
            )
            cur.execute("DELETE FROM plat.usuario WHERE id = %s", (id,))
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    return Response(status_code=204)
