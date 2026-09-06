"""Rotas do modelo genérico de conexão externa (item L6-02-a-modelo-conexao-e-seguranca; ADR 0012).

`GET /api/conexoes` lista as do inquilino (RLS); `POST /api/conexoes` cria (privilégio
`conteudo.registrar_fonte`, mesmo da rota de acervo) — a URL passa por `app.conexao.seguranca.validar_url`
ANTES do INSERT (recusa SSRF na entrada, não só no teste); `GET/PATCH/DELETE /api/conexoes/{id}` seguem
dono-ou-`conteudo.editar_tudo`, como pasta. `POST /api/conexoes/{id}/testar` é o teste de saúde: chama
`app.conexao.seguranca.buscar_seguro` com timeout curto e grava `saude`/`saude_mensagem`/
`saude_verificada_em`/`saude_latencia_ms`. Nenhuma rota devolve `credencial_cifrada` nem grava a credencial em
log (a credencial NUNCA aparece em `request`/`response` deste módulo depois de decifrada; só existe dentro do
corpo de `_testar`, e some do escopo ao final da função)."""

import json

import psycopg2
from fastapi import APIRouter, Request

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import registrar_evento, uuid_ok
from app.conexao import credencial as credencial_mod
from app.conexao import seguranca
from app.conexao.modelos import Conexao, ConexaoEditar, ConexaoEntrada, ConexaoPagina, ConexaoTeste
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/api/conexoes", tags=["conexoes"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}

# nunca inclui credencial_cifrada
CAMPOS = (
    "c.id, c.tipo, c.modo, c.nome, c.url, c.config, (c.credencial_cifrada IS NOT NULL) AS tem_credencial, "
    "c.saude, c.saude_mensagem, c.saude_latencia_ms, c.saude_verificada_em, c.criado_em, c.atualizado_em, "
    "c.dono_id, u.login AS dono_login, u.nome AS dono_nome"
)
SQL_BASE = f"SELECT {CAMPOS} FROM plat.conexao c JOIN plat.usuario u ON u.id = c.dono_id"  # noqa: S608


def _json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "tipo": r["tipo"],
        "modo": r["modo"],
        "nome": r["nome"],
        "url": r["url"],
        "config": r["config"] or {},
        "tem_credencial": bool(r["tem_credencial"]),
        "saude": r["saude"],
        "saude_mensagem": r["saude_mensagem"],
        "saude_latencia_ms": r["saude_latencia_ms"],
        "saude_verificada_em": iso(r["saude_verificada_em"]),
        "dono": {"id": r["dono_id"], "login": r["dono_login"], "nome": r["dono_nome"]},
        "criado_em": iso(r["criado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


def _carregar(cur, cid: str) -> dict:
    cur.execute(SQL_BASE + " WHERE c.id = %s::uuid", (cid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "conexao_inexistente", "conexão inexistente")
    return r


def _pode_editar(r: dict, auth: Auth) -> None:
    if r["dono_id"] != auth.usuario_id and not auth.tem("conteudo.editar_tudo"):
        raise ErroAPI(403, "sem_permissao", "só o dono da conexão ou conteudo.editar_tudo")


def _config_ok(config: dict) -> None:
    tamanho = len(json.dumps(config, ensure_ascii=False).encode("utf-8"))
    if tamanho > limites.CONEXAO_CONFIG_MAX_BYTES:
        raise ErroAPI(
            422, "config_grande_demais",
            f"config passa de {limites.CONEXAO_CONFIG_MAX_BYTES} bytes ({tamanho})",
        )


def _url_ok(url: str) -> None:
    """Recusa SSRF já na entrada (criar/editar), não só no teste de saúde: uma conexão nunca fica registrada
    com URL que o proxy jamais poderia buscar."""
    try:
        seguranca.validar_url(url)
    except seguranca.ErroURLInsegura as e:
        raise ErroAPI(422, "url_insegura", f"URL recusada: {e.motivo}", {"motivo": e.motivo}) from e


@router.get("", response_model=ConexaoPagina, openapi_extra=LER)
def listar(tipo: str | None = None, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    onde, params = ["true"], []
    if tipo:
        onde.append("c.tipo = %s")
        params.append(tipo)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        cur.execute(f"SELECT count(*) AS n FROM plat.conexao c WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(f"{SQL_BASE} WHERE {filtro} ORDER BY lower(c.nome)", params)  # noqa: S608
        itens = [_json(r) for r in cur.fetchall()]
    return {"total": total, "itens": itens}


@router.get("/{id}", response_model=Conexao, openapi_extra=LER)
def ver(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        return _json(_carregar(cur, cid))


@router.post("", response_model=Conexao, status_code=201, openapi_extra=CRIAR)
def criar(corpo: ConexaoEntrada, request: Request, auth: Auth = autenticado("conteudo.criar")):
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    _url_ok(corpo.url)
    _config_ok(corpo.config)
    credencial_cifrada = credencial_mod.cifrar(corpo.credencial, settings.PLAT_SECRET) if corpo.credencial else None
    with db.db(auth.contexto()) as cur:
        try:
            cur.execute(
                "INSERT INTO plat.conexao(tenant_id, tipo, modo, nome, url, config, credencial_cifrada, dono_id) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s) RETURNING id",
                (
                    auth.tenant_id, corpo.tipo, corpo.modo, " ".join(corpo.nome.split()), corpo.url,
                    json.dumps(corpo.config, ensure_ascii=False), credencial_cifrada, auth.usuario_id,
                ),
            )
            cid = str(cur.fetchone()["id"])
        except psycopg2.errors.UniqueViolation as e:
            raise ErroAPI(409, "nome_existente", "já existe uma conexão com esse nome") from e
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(
            cur, request, "conexoes/criar", "conexao", cid, {"tipo": corpo.tipo, "nome": corpo.nome, "modo": corpo.modo}
        )
        return _json(_carregar(cur, cid))


@router.patch("/{id}", response_model=Conexao, openapi_extra=EDITAR)
def editar(id: str, corpo: ConexaoEditar, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        campos, params = [], []
        if corpo.nome is not None:
            campos.append("nome = %s")
            params.append(" ".join(corpo.nome.split()))
        if corpo.url is not None:
            _url_ok(corpo.url)
            campos.append("url = %s")
            params.append(corpo.url)
            campos.append("saude = 'nunca_testada'")  # URL mudou: a saúde anterior não vale mais para a nova
        if corpo.modo is not None:
            campos.append("modo = %s")
            params.append(corpo.modo)
        if corpo.config is not None:
            _config_ok(corpo.config)
            campos.append("config = %s::jsonb")
            params.append(json.dumps(corpo.config, ensure_ascii=False))
        if corpo.remover_credencial:
            campos.append("credencial_cifrada = NULL")
        elif corpo.credencial is not None:
            campos.append("credencial_cifrada = %s")
            params.append(credencial_mod.cifrar(corpo.credencial, settings.PLAT_SECRET))
        if campos:
            try:
                cur.execute(f"UPDATE plat.conexao SET {', '.join(campos)} WHERE id = %s::uuid", (*params, cid))  # noqa: S608
            except psycopg2.errors.UniqueViolation as e:
                raise ErroAPI(409, "nome_existente", "já existe uma conexão com esse nome") from e
            except psycopg2.Error as e:
                raise auth_comum.erro_do_banco(e) from e
            campos_alterados = [c.split(" =")[0] for c in campos]
            registrar_evento(cur, request, "conexoes/editar", "conexao", cid, {"campos": campos_alterados})
        return _json(_carregar(cur, cid))


@router.delete("/{id}", status_code=204, openapi_extra=EDITAR)
def apagar(id: str, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        cur.execute("DELETE FROM plat.conexao WHERE id = %s::uuid", (cid,))
        registrar_evento(cur, request, "conexoes/apagar", "conexao", cid, {"nome": r["nome"]})


@router.post("/{id}/testar", response_model=ConexaoTeste, openapi_extra=EDITAR)
def testar(id: str, request: Request, auth: Auth = autenticado()):
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
        _pode_editar(r, auth)
        url = r["url"]

    # decifra a credencial só em memória, só aqui, e só para autenticar o teste — nunca volta na resposta
    cabecalhos = None
    if r["tem_credencial"]:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (cid,))
            bruta = cur.fetchone()["credencial_cifrada"]
        try:
            token = credencial_mod.decifrar(bruta, settings.PLAT_SECRET)
            cabecalhos = {"Authorization": f"Bearer {token}"}
        except ValueError:
            cabecalhos = None  # PLAT_SECRET trocado ou dado corrompido: testa sem credencial, nunca quebra a rota

    resultado = seguranca.buscar_seguro(
        url, metodo="GET", timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S,
        timeout_ler=limites.CONEXAO_LER_TIMEOUT_S, cabecalhos=cabecalhos,
    )
    saude = "ok" if resultado.ok else "erro"
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "UPDATE plat.conexao SET saude = %s, saude_mensagem = %s, saude_latencia_ms = %s, "
            "saude_verificada_em = now() WHERE id = %s::uuid RETURNING saude_verificada_em",
            (saude, resultado.mensagem, resultado.latencia_ms, cid),
        )
        verificada_em = cur.fetchone()["saude_verificada_em"]
        registrar_evento(
            cur, request, "conexoes/testar", "conexao", cid,
            {"ok": resultado.ok, "status": resultado.status, "mensagem": resultado.mensagem},
        )
    return {
        "ok": resultado.ok, "status": resultado.status, "mensagem": resultado.mensagem,
        "latencia_ms": resultado.latencia_ms, "saude": saude, "saude_verificada_em": iso(verificada_em),
    }
