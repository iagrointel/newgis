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
import uuid

import psycopg2
from fastapi import APIRouter, Request

from app import db, limites
from app.auth import comum as auth_comum
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo import comum as catalogo_comum
from app.catalogo import documento as catalogo_documento
from app.catalogo import tipos as catalogo_tipos
from app.catalogo.comum import registrar_evento, uuid_ok
from app.catalogo.modelos import Item as ItemSaida
from app.conexao import credencial as credencial_mod
from app.conexao import proveniencia, seguranca
from app.conexao.modelos import (
    Conexao,
    ConexaoEditar,
    ConexaoEntrada,
    ConexaoPagina,
    ConexaoTeste,
    PublicarCamadaEntrada,
    SaudeHistoricoPagina,
)
from app.erros import ErroAPI
from app.seguranca_rotacao import decifrar_com_rotacao
from app.settings import settings

router = APIRouter(prefix="/api/conexoes", tags=["conexoes"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CRIAR = {"x-auth": "S/T", "x-privilegio": "conteudo.registrar_fonte"}
EDITAR = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}
HISTORICO_LIMITE_PADRAO = 10
HISTORICO_LIMITE_MAX = 30  # o mesmo teto de guarda de plat.conexao_saude_historico (036)

# nunca inclui credencial_cifrada
CAMPOS = (
    "c.id, c.tipo, c.modo, c.nome, c.url, c.config, (c.credencial_cifrada IS NOT NULL) AS tem_credencial, "
    "c.saude, c.saude_mensagem, c.saude_latencia_ms, c.saude_verificada_em, c.criado_em, c.atualizado_em, "
    "c.dono_id, u.login AS dono_login, u.nome AS dono_nome, "
    "v.estado_saude, v.disponibilidade_30d_pct, v.disponibilidade_30d_total"
)
# LEFT JOIN (nunca INNER): a view sempre tem 1 linha por conexão (FROM plat.conexao), mas o LEFT deixa explícito
# que a ausência de histórico não pode sumir com a conexão da listagem (item L6-02-l-saude).
SQL_BASE = (
    f"SELECT {CAMPOS} FROM plat.conexao c JOIN plat.usuario u ON u.id = c.dono_id "  # noqa: S608
    "LEFT JOIN plat.v_conexao_saude v ON v.conexao_id = c.id"
)


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
        "estado_saude": r.get("estado_saude") or "nunca_testada",
        "disponibilidade_30d_pct": (
            float(r["disponibilidade_30d_pct"]) if r.get("disponibilidade_30d_pct") is not None else None
        ),
        "disponibilidade_30d_total": r.get("disponibilidade_30d_total") or 0,
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
            token = decifrar_com_rotacao(
                credencial_mod.decifrar, bruta, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR
            )
            cabecalhos = {"Authorization": f"Bearer {token}"}
        except Exception:  # noqa: BLE001 — PLAT_SECRET (e ANTERIOR) trocados ou dado corrompido: testa sem
            # credencial, nunca quebra a rota (InvalidTag do AEAD não é ValueError — abrangido de propósito)
            cabecalhos = None

    resultado = seguranca.buscar_seguro(
        url, metodo="GET", timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S,
        timeout_ler=limites.CONEXAO_LER_TIMEOUT_S, cabecalhos=cabecalhos,
    )
    saude = "ok" if resultado.ok else "erro"
    with db.db(auth.contexto()) as cur:
        # plat.conexao_saude_registrar (036) grava saude/saude_mensagem/... E o histórico (item L6-02-l-saude)
        # numa função só, com a poda de 30 linhas — o UPDATE direto de antes nunca alimentava o histórico.
        cur.execute(
            "SELECT plat.conexao_saude_registrar(%s::uuid, %s, %s, %s, %s)",
            (cid, resultado.ok, resultado.status, resultado.mensagem, resultado.latencia_ms),
        )
        cur.execute("SELECT saude_verificada_em FROM plat.conexao WHERE id = %s::uuid", (cid,))
        verificada_em = cur.fetchone()["saude_verificada_em"]
        registrar_evento(
            cur, request, "conexoes/testar", "conexao", cid,
            {"ok": resultado.ok, "status": resultado.status, "mensagem": resultado.mensagem},
        )
    return {
        "ok": resultado.ok, "status": resultado.status, "mensagem": resultado.mensagem,
        "latencia_ms": resultado.latencia_ms, "saude": saude, "saude_verificada_em": iso(verificada_em),
    }


@router.get("/{id}/saude-historico", response_model=SaudeHistoricoPagina, openapi_extra=LER)
def saude_historico(
    id: str, limite: int = HISTORICO_LIMITE_PADRAO, auth: Auth = autenticado(escopo_token="catalogo:ler")
):
    """Últimos testes de saúde da conexão (item L6-02-l-saude), mais recente primeiro; `limite` (padrão 10, teto
    30 — o mesmo teto de guarda de `plat.conexao_saude_historico`) evita que a tela peça mais do que existe."""
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    limite = max(1, min(limite, HISTORICO_LIMITE_MAX))
    with db.db(auth.contexto()) as cur:
        _carregar(cur, cid)  # 404 se a conexão não existe ou não é visível a este inquilino (RLS)
        cur.execute(
            "SELECT verificada_em, ok, status, mensagem, latencia_ms FROM plat.conexao_saude_historico "
            "WHERE conexao_id = %s::uuid ORDER BY verificada_em DESC LIMIT %s",
            (cid, limite),
        )
        itens = [
            {
                "verificada_em": iso(row["verificada_em"]), "ok": row["ok"], "status": row["status"],
                "mensagem": row["mensagem"], "latencia_ms": row["latencia_ms"],
            }
            for row in cur.fetchall()
        ]
    return {"itens": itens}


@router.post("/{id}/publicar", response_model=ItemSaida, status_code=201, openapi_extra=CRIAR)
def publicar_camada(
    id: str, request: Request, corpo: PublicarCamadaEntrada | None = None,
    auth: Auth = autenticado("conteudo.criar"),
):
    """Cria um item de catálogo (tipo `conexao`, `dados.parametros.conexao_id` apontando para esta linha) com a
    ficha de procedência preenchida do que o SERVIÇO EXTERNO declara agora (item L6-05-proveniencia-camada-
    externa) — nunca um valor padrão; campo que o serviço não declara fica `None` (a tela mostra "não
    registrado"). `creditos` do item recebe a atribuição lida (o mais perto de "legenda" que existe hoje: o
    L6-02-b, que desenha a camada no mapa de verdade, ainda não foi construído)."""
    if not auth.tem("conteudo.registrar_fonte"):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio conteudo.registrar_fonte",
            {"exigido": "conteudo.registrar_fonte"},
        )
    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)

    descoberta = proveniencia.descobrir(r)  # I/O de rede FORA da transação (mesma regra de ContextoJob)
    dados_item = {
        "protocolo": r["tipo"], "url": r["url"], "parametros": {"conexao_id": cid},
        "procedencia": descoberta.procedencia,
    }
    catalogo_tipos.validar("conexao", dados_item)
    catalogo_documento.validar_grafo("conexao", dados_item)
    titulo = ((corpo.titulo if corpo else None) or r["nome"]).strip()[:250]
    atribuicao = (descoberta.atribuicao or "")[:2048] or None
    iid = str(uuid.uuid4())
    with db.db(auth.contexto()) as cur:
        cur.execute(
            "SELECT plat.cota_itens(%s) AS cota, (SELECT count(*) FROM plat.item WHERE tenant_id = %s) AS n",
            (auth.tenant_id, auth.tenant_id),
        )
        rc = cur.fetchone()
        if rc["n"] >= rc["cota"]:
            raise ErroAPI(
                413, "cota_itens", f"cota de itens do inquilino esgotada ({rc['cota']})", {"cota": rc["cota"]}
            )
        try:
            cur.execute(
                "INSERT INTO plat.item(id, tenant_id, tipo, titulo, creditos, dono_id, dados, origem, url, "
                "criado_por, modificado_por) "
                "VALUES (%s::uuid, %s, 'conexao', %s, %s, %s, %s, 'referenciado', %s, %s, %s)",
                (
                    iid, auth.tenant_id, titulo, atribuicao, auth.usuario_id, catalogo_comum.jsonb(dados_item),
                    r["url"], auth.usuario_id, auth.usuario_id,
                ),
            )
        except psycopg2.Error as e:
            raise auth_comum.erro_do_banco(e) from e
        registrar_evento(
            cur, request, "conexoes/publicar_camada", "item", iid,
            {"conexao_id": cid, "tipo": r["tipo"], "licenca_declarada": bool(descoberta.procedencia.get("licenca"))},
        )
        return catalogo_comum.item_json(catalogo_comum.item_ou_404(cur, iid), auth)
