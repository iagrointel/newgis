"""Rotas do catálogo de conectores públicos (item L6-02-m-catalogo-endpoints-brasil). `GET /api/endpoints-publicos`
lista as entradas VIVAS (último teste HTTP verde), com filtro por tipo/órgão/texto; `?vivo=false` devolve a seção
"fora do ar" (entrada cujo último teste falhou: saiu da lista principal, não do catálogo — volta sozinha quando o
reteste semanal passar). `GET /api/endpoints-publicos/{id}` é a ficha; `POST /api/endpoints-publicos/{id}/adicionar`
é o "um clique": cria a `plat.conexao` do inquilino (tipo = o da entrada, modo referenciada) com a ficha de
procedência do catálogo em `config.procedencia` (órgão, licença, data do teste, comando de reexecução) — idempotente
por (tipo, url): segundo clique devolve a mesma conexão com `criada: false`. Entrada fora do ar não vira conexão
(409 `endpoint_fora_do_ar`): quem quiser mesmo assim cola a URL em `POST /api/conexoes`. A tabela é global e só de
leitura para a aplicação (escrita só pelo job `endpoints_publicos.retestar`)."""

from __future__ import annotations

import datetime
import json

import psycopg2
from fastapi import APIRouter, Query, Request

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.comum import paginacao
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento
from app.conexao import endpoints_publicos
from app.conexao.modelos import Conexao, Saida
from app.conexao.rotas import _carregar, _json
from app.erros import ErroAPI

router = APIRouter(prefix="/api/endpoints-publicos", tags=["conexoes"])
LER = {"x-auth": "S/T", "x-privilegio": "conteudo.ver_inquilino"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
CAMPOS = (
    "id, slug, orgao, nome, tipo, url, licenca, origem, fonte_id, vivo, http, content_type, ms, motivo, testado_em, "
    "primeiro_ok_em, falhas_seguidas"
)


class EndpointPublico(Saida):
    id: int
    slug: str
    orgao: str
    nome: str
    tipo: str
    url: str
    licenca: str
    origem: str
    fonte_id: str | None = None
    vivo: bool | None = None
    http: int | None = None
    ms: int | None = None
    motivo: str | None = None
    testado_em: str | None = None
    primeiro_ok_em: str | None = None
    falhas_seguidas: int = 0


class EndpointPublicoPagina(Saida):
    total: int
    vivos: int
    fora_do_ar: int
    nunca_testados: int
    testado_em_ultimo: str | None = None
    itens: list[EndpointPublico]


class ConexaoAdicionada(Conexao):
    criada: bool


def _linha(r: dict) -> dict:
    j = dict(r)
    j["testado_em"] = iso(r["testado_em"])
    j["primeiro_ok_em"] = iso(r["primeiro_ok_em"])
    return j


@router.get("", response_model=EndpointPublicoPagina, openapi_extra=LER)
def listar(
    tipo: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    vivo: bool = True,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado("conteudo.ver_inquilino", escopo_token="catalogo:ler"),
):
    lim, desl = paginacao(limite, deslocamento, maximo=limites.ENDPOINT_PUBLICO_PAGINA_MAX)
    onde, params = ["vivo IS NOT DISTINCT FROM %s"], [vivo]
    if tipo:
        if tipo not in endpoints_publicos.TIPOS:
            raise ErroAPI(422, "validacao", f"tipo entre {', '.join(endpoints_publicos.TIPOS)}", {"campo": "tipo"})
        onde.append("tipo = %s")
        params.append(tipo)
    if q:
        onde.append("(nome ILIKE %s OR orgao ILIKE %s OR url ILIKE %s)")
        params.extend([f"%{q}%"] * 3)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT count(*) FILTER (WHERE vivo) AS vivos, count(*) FILTER (WHERE vivo = false) AS fora_do_ar, "
            "count(*) FILTER (WHERE vivo IS NULL) AS nunca_testados, max(testado_em) AS ultimo "
            "FROM plat.endpoint_publico"
        )
        c = cur.fetchone()
        cur.execute(f"SELECT count(*) AS n FROM plat.endpoint_publico WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT {CAMPOS} FROM plat.endpoint_publico WHERE {filtro} "  # noqa: S608
            "ORDER BY orgao, nome, tipo LIMIT %s OFFSET %s",
            [*params, lim, desl],
        )
        itens = [_linha(r) for r in cur.fetchall()]
    return {
        "total": total, "vivos": c["vivos"], "fora_do_ar": c["fora_do_ar"], "nunca_testados": c["nunca_testados"],
        "testado_em_ultimo": iso(c["ultimo"]), "itens": itens,
    }


def _ficha(cur, eid: int) -> dict:
    cur.execute(f"SELECT {CAMPOS} FROM plat.endpoint_publico WHERE id = %s", (eid,))  # noqa: S608
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "endpoint_inexistente", "entrada inexistente no catálogo de conectores públicos")
    return r


@router.get("/{id}", response_model=EndpointPublico, openapi_extra=LER)
def ver(id: int, auth: Auth = autenticado("conteudo.ver_inquilino", escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return _linha(_ficha(cur, id))


def procedencia_do_catalogo(e: dict, data_de_acesso: str) -> dict:
    """ficha de 10 campos (decisão B11) do que o CATÁLOGO sabe; o `publicar` da conexão completa com o que o
    serviço vivo declarar (GetCapabilities/f=json), como em qualquer conexão."""
    testado = iso(e["testado_em"]) if e.get("testado_em") else None
    return {
        "fonte": e["orgao"],
        "url": e["url"],
        "licenca": None if e["licenca"] == "nao-declarada" else e["licenca"],
        "data_do_dado": None,
        "data_de_acesso": data_de_acesso,
        "metodo": (
            f"catálogo de conectores públicos da plataforma (origem {e['origem']}"
            f"{', fonte ' + e['fonte_id'] if e.get('fonte_id') else ''}); serviço {e['tipo']} testado por HTTP em "
            f"{testado or 'data não registrada'} ({e.get('motivo') or 'sem resultado'})"
        ),
        "confianca": "declarado" if e["licenca"] != "nao-declarada" else None,
        "frescor": (
            f"último teste HTTP do catálogo em {testado}; reteste a cada {limites.ENDPOINT_PUBLICO_RETESTE_DIAS} dias"
            if testado else "entrada ainda não testada pelo catálogo"
        ),
        "sha256": None,
        "comando_reexecucao": f"GET {endpoints_publicos.url_de_teste(e['url'], e['tipo'])}",
        "limites": None if e["licenca"] != "nao-declarada" else [
            "licença não declarada pelo órgão em página própria (vocabulário B3): conferir o termo de uso "
            "antes de publicar"
        ],
        "responsavel": e["orgao"],
        "catalogo_endpoint_id": e["id"],
    }


@router.post("/{id}/adicionar", response_model=ConexaoAdicionada, status_code=201, openapi_extra=CRIAR)
def adicionar(id: int, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    with db.db(auth.contexto()) as cur:
        e = _ficha(cur, id)
        if e["vivo"] is not True:
            raise ErroAPI(
                409, "endpoint_fora_do_ar",
                "entrada fora do ar no último teste do catálogo: não vira conexão daqui "
                "(cole a URL em POST /api/conexoes se quiser mesmo assim)",
                {"motivo": e["motivo"], "testado_em": iso(e["testado_em"]) if e["testado_em"] else None},
            )
        cur.execute(
            "SELECT id FROM plat.conexao WHERE tipo = %s AND url = %s ORDER BY criado_em LIMIT 1", (e["tipo"], e["url"])
        )
        r = cur.fetchone()
        criada = r is None
        cid = str(r["id"]) if r else None
        if criada:
            hoje = datetime.datetime.now(datetime.UTC).date().isoformat()
            config = {"endpoint_publico_id": e["id"], "procedencia": procedencia_do_catalogo(e, hoje)}
            nome = " ".join(f"{e['orgao']} · {e['nome']}".split())[: limites.CONEXAO_NOME_MAX]
            curto = nome[: limites.CONEXAO_NOME_MAX - 6]
            for tentativa in range(3):
                try:
                    cur.execute("SAVEPOINT endpoint_adicionar")
                    cur.execute(
                        "INSERT INTO plat.conexao(tenant_id, tipo, modo, nome, url, config, dono_id) "
                        "VALUES (%s, %s, 'referenciada', %s, %s, %s::jsonb, %s) RETURNING id",
                        (
                            auth.tenant_id, e["tipo"], nome if tentativa == 0 else f"{curto} ({tentativa + 1})",
                            e["url"], json.dumps(config, ensure_ascii=False), auth.usuario_id,
                        ),
                    )
                    cid = str(cur.fetchone()["id"])
                    cur.execute("RELEASE SAVEPOINT endpoint_adicionar")
                    break
                except psycopg2.errors.UniqueViolation:
                    cur.execute("ROLLBACK TO SAVEPOINT endpoint_adicionar")
                except psycopg2.Error as exc:
                    raise auth_comum.erro_do_banco(exc) from exc
            if cid is None:
                raise ErroAPI(409, "nome_existente", "já existe uma conexão com esse nome (3 variações tentadas)")
            registrar_evento(
                cur, request, "conexoes/criar", "conexao", cid,
                {"tipo": e["tipo"], "nome": nome, "modo": "referenciada", "origem": "endpoint_publico",
                 "endpoint_id": e["id"]},
            )
        saida = _json(_carregar(cur, cid))
    saida["criada"] = criada
    return saida
