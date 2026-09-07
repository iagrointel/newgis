"""Rotas da rede de utilidades (item L4-01-a-pacote-de-ativos; ADR 0019).

`/api/rede` cria e lista as redes do inquilino; `POST /api/rede/{rede_id}/pacote` importa um pacote de ativos
(corpo = o arquivo JSON, cru) e `GET /api/rede/{rede_id}/pacote` devolve o mesmo pacote em forma canônica,
reconstruído das tabelas. `/api/rede/pacotes` lista os pacotes que vêm com a instalação e entrega o arquivo de
cada um, para que o cliente possa importar sem ter o arquivo em mãos.

A escrita exige o privilégio `rede.editar` (semeado na migração 003, "editar rede de utilidades"); a leitura
segue a visibilidade por inquilino (RLS). O corpo do pacote é lido CRU, sem passar por pydantic: a mensagem de
erro precisa apontar a linha do arquivo enviado, e reserializar o corpo perderia essa referência.

⛔ Nome do caminho: o portão do item dizia `/api/v1/rede/...`. O produto inteiro (74 rotas) responde em `/api/`
sem prefixo de versão, e a versão do pacote está DENTRO do documento (`esquema_versao`). Manter o `v1` só nesta
linha criaria duas convenções de URL na mesma API. Decisão registrada no ADR 0019 seção 6; os demais itens da
linha L4 seguem `/api/rede/...`."""

import hashlib
import uuid as uuid_mod

import psycopg2
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.erros import ErroAPI
from app.rede_utilidades import deposito, instalados
from app.rede_utilidades import pacote as pacote_mod
from app.rede_utilidades.modelos import (
    ImportacaoResultado,
    PacoteInstaladoLista,
    Rede,
    RedeEntrada,
    RedePagina,
)

router = APIRouter(prefix="/api/rede", tags=["rede de utilidades"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rede.editar"}
# catálogo que vem com a instalação: não é dado de inquilino nenhum (mesmo valor de /api/rota e /api/eu)
INSTALADO = {"x-auth": "S/T", "x-privilegio": "proprio"}
PACOTE_MAX_BYTES = 8 * 1024 * 1024  # bem acima do maior pacote entregue (94 KiB) e dentro do teto de corpo (10 MiB)

CONTAGENS = (
    "(SELECT count(*) FROM plat.rede_dominio d WHERE d.rede_id = r.id) AS n_dominios, "
    "(SELECT count(*) FROM plat.rede_tier t WHERE t.rede_id = r.id) AS n_tiers, "
    "(SELECT count(*) FROM plat.rede_categoria c WHERE c.rede_id = r.id) AS n_categorias, "
    "(SELECT count(*) FROM plat.rede_terminal_config tc WHERE tc.rede_id = r.id) AS n_terminais, "
    "(SELECT count(*) FROM plat.rede_grupo g WHERE g.rede_id = r.id) AS n_grupos, "
    "(SELECT count(*) FROM plat.rede_tipo tp WHERE tp.rede_id = r.id) AS n_tipos, "
    "(SELECT count(*) FROM plat.rede_atributo a WHERE a.rede_id = r.id) AS n_atributos, "
    "(SELECT count(*) FROM plat.rede_regra rg WHERE rg.rede_id = r.id) AS n_regras"
)
SQL_BASE = (
    "SELECT r.id, r.nome, r.disciplina, r.descricao, r.tolerancia_m, r.pacote_codigo, r.pacote_nome, r.pacote_versao, "
    "r.pacote_esquema_versao, r.pacote_fonte, r.pacote_sha256, r.pacote_bytes, r.importado_em, r.criado_em, "
    f"r.atualizado_em, r.dono_id, u.login AS dono_login, u.nome AS dono_nome, {CONTAGENS} "
    "FROM plat.rede r JOIN plat.usuario u ON u.id = r.dono_id"
)


def _json(r: dict) -> dict:
    pacote = None
    if r["pacote_codigo"]:
        pacote = {
            "codigo": r["pacote_codigo"], "nome": r["pacote_nome"], "versao": r["pacote_versao"],
            "esquema_versao": r["pacote_esquema_versao"], "fonte": r["pacote_fonte"],
            "sha256": r["pacote_sha256"], "bytes": r["pacote_bytes"], "importado_em": iso(r["importado_em"]),
        }
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "disciplina": r["disciplina"],
        "descricao": r["descricao"],
        "tolerancia_m": float(r["tolerancia_m"]),
        "pacote": pacote,
        "contagens": {s: r[f"n_{s}"] for s in pacote_mod.SECOES},
        "dono": {"id": r["dono_id"], "login": r["dono_login"], "nome": r["dono_nome"]},
        "criado_em": iso(r["criado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


def _uuid_ok(valor: str) -> str:
    try:
        return str(uuid_mod.UUID(valor))
    except (ValueError, AttributeError, TypeError) as e:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e


def _carregar(cur, rede_id: str) -> dict:
    cur.execute(SQL_BASE + " WHERE r.id = %s::uuid", (rede_id,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    return r


def _travar_rede(cur, rede_id: str) -> None:
    """`FOR UPDATE` na linha da rede antes de substituir o catálogo inteiro. Achado do turno 3 (item
    L4-01-a-pacote-de-ativos, achado A4): mover a importação para o threadpool corrige o laço de eventos
    travado, mas também torna REAL a concorrência que antes só existia no papel — duas importações na
    MESMA rede podem, de fato, apagar e gravar as 9 tabelas filhas ao mesmo tempo. Sem esta trava, isso às
    vezes vira `DeadlockDetected` (não é `psycopg2.errors.UniqueViolation`/`ForeignKeyViolation`/etc., logo
    `erro_do_banco` não tem para onde mapear e a resposta é 500). A trava faz a segunda importação ESPERAR
    a primeira terminar (commit ou rollback) e só então prosseguir — nunca as duas ao mesmo tempo."""
    cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid FOR UPDATE", (rede_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "rede_inexistente", "rede inexistente")


@router.get("/pacotes", response_model=PacoteInstaladoLista, openapi_extra=INSTALADO)
def listar_pacotes_instalados(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Pacotes de ativos entregues com a instalação. Não lê nem escreve dado de inquilino."""
    itens = [{k: v for k, v in ficha.items() if k != "arquivo"} for ficha in instalados.catalogo().values()]
    return {"total": len(itens), "itens": sorted(itens, key=lambda f: f["codigo"])}


@router.get("/pacotes/{codigo}", openapi_extra=INSTALADO, response_class=Response)
def baixar_pacote_instalado(codigo: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O arquivo do pacote instalado, byte a byte como está no disco (é o que se envia de volta na importação)."""
    bruto = instalados.bruto(codigo)
    if bruto is None:
        raise ErroAPI(404, "pacote_inexistente", "não há pacote instalado com esse código")
    return Response(
        content=bruto,
        media_type="application/json; charset=utf-8",
        headers={"ETag": '"' + hashlib.sha256(bruto).hexdigest() + '"', "Cache-Control": "no-store"},
    )


@router.get("", response_model=RedePagina, openapi_extra=LER)
def listar(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.rede")
        total = cur.fetchone()["n"]
        cur.execute(SQL_BASE + " ORDER BY lower(r.nome)")
        return {"total": total, "itens": [_json(r) for r in cur.fetchall()]}


@router.post("", response_model=Rede, status_code=201, openapi_extra=EDITAR)
def criar(corpo: RedeEntrada, request: Request, auth: Auth = autenticado("rede.editar")):
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.rede(tenant_id, nome, disciplina, descricao, tolerancia_m, dono_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (auth.tenant_id, " ".join(corpo.nome.split()), corpo.disciplina, corpo.descricao,
                 corpo.tolerancia_m, auth.usuario_id),
            )
            rede_id = str(cur.fetchone()["id"])
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe uma rede com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/criar", "rede", rede_id,
                         {"nome": corpo.nome, "disciplina": corpo.disciplina})
        return _json(_carregar(cur, rede_id))


@router.get("/{rede_id}", response_model=Rede, openapi_extra=LER)
def ver(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return _json(_carregar(cur, _uuid_ok(rede_id)))


@router.delete("/{rede_id}", status_code=204, openapi_extra=EDITAR)
def apagar(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, rid)
        cur.execute("DELETE FROM plat.rede WHERE id = %s::uuid", (rid,))
        registrar_evento(cur, request, "redes/apagar", "rede", rid, {"nome": r["nome"]})
    return Response(status_code=204)


def _importar_pacote_sincrono(rid: str, bruto: bytes, auth: Auth, request: Request) -> dict:
    """Validação (CPU) e gravação (psycopg2, bloqueante) do pacote — tudo o que `importar_pacote` fazia dentro
    do laço de eventos (achado A4, `L4-01-a-pacote-de-ativos`, adversário do turno 3). Um pacote de 1,15 MB com
    4 mil problemas segurava `/saude` da API inteira, de qualquer inquilino, por 13,5 s; roda em thread à parte
    para o laço de eventos continuar respondendo a todo mundo."""
    if len(bruto) > PACOTE_MAX_BYTES:
        raise ErroAPI(413, "pacote_grande_demais",
                      f"o pacote passa de {PACOTE_MAX_BYTES} bytes ({len(bruto)})")
    # A REDE PRIMEIRO, o corpo depois: quem não pode ver esta rede recebe 404 sem que o corpo diga nada
    # sobre ela. Sem esta consulta, um pacote malformado apontado para a rede de OUTRO inquilino devolvia
    # 422 de esquema — a resposta dependia do corpo antes da autorização, e a varredura cruzada A→B
    # reprovava (`tests/api/test_cruzado.py`). É uma leitura barata, sob RLS, fora do laço de eventos.
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT 1 FROM plat.rede WHERE id = %s::uuid", (rid,))
        if cur.fetchone() is None:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente")
    try:
        doc = pacote_mod.ler(bruto)
    except pacote_mod.ErroPacote as e:
        raise ErroAPI(422, "pacote_invalido",
                      f"o pacote foi recusado: {len(e.problemas)} problema(s)", e.problemas) from e
    sha = hashlib.sha256(bruto).hexdigest()
    with db.db(auth.contexto()) as cur:
        _travar_rede(cur, rid)  # 404 antes de apagar coisa alguma; FOR UPDATE serializa importações concorrentes
        try:
            contagens = deposito.importar(cur, auth.tenant_id, rid, doc, auth.usuario_id, sha, len(bruto))
        except LookupError as e:
            raise ErroAPI(404, "rede_inexistente", "rede inexistente") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(cur, request, "redes/importar_pacote", "rede", rid,
                         {"codigo": doc["pacote"]["codigo"], "versao": doc["pacote"]["versao"],
                          "sha256": sha, "contagens": contagens})
    return {
        "rede_id": rid, "codigo": doc["pacote"]["codigo"], "versao": doc["pacote"]["versao"],
        "esquema_versao": doc["esquema_versao"], "sha256": sha, "bytes": len(bruto), "contagens": contagens,
    }


@router.post("/{rede_id}/pacote", response_model=ImportacaoResultado, status_code=201, openapi_extra=EDITAR)
async def importar_pacote(rede_id: str, request: Request, auth: Auth = autenticado("rede.editar")):
    """Importa o pacote de ativos. Substitui o catálogo INTEIRO da rede, numa transação: ou entra tudo, ou nada.
    Só a leitura do corpo fica no laço de eventos (rápida, I/O); validação e gravação vão para o threadpool."""
    rid = _uuid_ok(rede_id)
    bruto = await request.body()
    return await run_in_threadpool(_importar_pacote_sincrono, rid, bruto, auth, request)


@router.get("/{rede_id}/pacote", openapi_extra=LER, response_class=Response)
def exportar_pacote(rede_id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O pacote da rede, reconstruído das tabelas e serializado na forma canônica — nunca o arquivo recebido."""
    rid = _uuid_ok(rede_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, rid)
        doc = deposito.exportar(cur, rid)
    if doc is None:
        raise ErroAPI(404, "pacote_inexistente", "esta rede ainda não recebeu um pacote de ativos")
    bruto = pacote_mod.canonizar(doc)
    return Response(
        content=bruto,
        media_type="application/json; charset=utf-8",
        headers={"ETag": '"' + hashlib.sha256(bruto).hexdigest() + '"', "Cache-Control": "no-store"},
    )
