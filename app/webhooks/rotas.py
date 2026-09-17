"""Rotas de webhook por inquilino (item L7-08-a), sob o privilégio `org.integracoes` (semeado na 003
com a descrição "SSO, SMTP, webhooks, CORS" — a mesma chave das rotas de SMTP, app/correio/rotas_smtp.py).

`POST /api/webhooks` cria e devolve o segredo UMA única vez (`WebhookSegredo`); perdê-lo significa
rotacionar. A URL é recusada JÁ na entrada (SSRF, `assinatura.validar_url` — o mesmo padrão de
`app/conexao/rotas.py::_url_ok`), e os nomes de evento são conferidos contra `plat.evento_tipo` —
assinar evento inexistente é erro de digitação, não configuração válida. O segredo NUNCA sai em
listagem, detalhe, log nem evento; a entrega em si é o job `webhooks.entregar` (tarefas.py), disparado
pelo gatilho sobre `plat.evento`."""

from fastapi import APIRouter, Request
from pydantic import ValidationError

from app import db
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import uuid_ok
from app.conexao import seguranca
from app.erros import ErroAPI
from app.jobs import sistema
from app.settings import settings
from app.webhooks import assinatura
from app.webhooks.modelos import (
    Entrega,
    EntregaPagina,
    Webhook,
    WebhookEditar,
    WebhookEntrada,
    WebhookPagina,
    WebhookSegredo,
)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
PRIV = {"x-auth": "S/T", "x-privilegio": "org.integracoes"}
CAMPOS = (
    "w.id, w.nome, w.url, w.eventos, w.ativo, w.falhas_consecutivas, w.desativada_em, "
    "w.desativada_motivo, w.criado_em, w.criado_por, u.login AS criado_por_login"
)
ENTREGA_LIMITE_PADRAO = 20
ENTREGA_LIMITE_MAX = 100
ESTADOS_ENTREGA = ("pendente", "entregue", "falhou", "desativada")


def _webhook_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "url": r["url"],
        "eventos": list(r["eventos"] or []),
        "ativo": bool(r["ativo"]),
        "falhas_consecutivas": r["falhas_consecutivas"],
        "desativada_em": iso(r["desativada_em"]),
        "desativada_motivo": r["desativada_motivo"],
        "criado_em": iso(r["criado_em"]),
        "criado_por": str(r["criado_por"]) if r["criado_por"] else None,
        "criado_por_login": r["criado_por_login"],
    }


def _entrega_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "webhook_id": str(r["webhook_id"]),
        "evento_id": r["evento_id"],
        "tipo_evento": r["tipo_evento"],
        "payload": r["payload"],
        "estado": r["estado"],
        "tentativas": r["tentativas"],
        "reenvios": r["reenvios"],
        "ultima_status": r["ultima_status"],
        "ultima_erro": r["ultima_erro"],
        "criado_em": iso(r["criado_em"]),
        "entregue_em": iso(r["entregue_em"]),
    }


def _url_ok(url: str) -> None:
    try:
        assinatura.validar_url(url)
    except seguranca.ErroURLInsegura as e:
        raise ErroAPI(422, "url_insegura", f"URL recusada: {e.motivo}", {"motivo": e.motivo}) from e


def _eventos_ok(cur, eventos: list[str]) -> None:
    if len(set(eventos)) != len(eventos):
        raise ErroAPI(422, "evento_repetido", "a lista de eventos não pode repetir tipos")
    cur.execute("SELECT nome FROM plat.evento_tipo WHERE nome = ANY(%s)", (eventos,))
    conhecidos = {r["nome"] for r in cur.fetchall()}
    faltando = sorted(set(eventos) - conhecidos)
    if faltando:
        raise ErroAPI(422, "evento_desconhecido",
                      "tipos de evento fora de plat.evento_tipo", {"desconhecidos": faltando})


def _carregar(cur, wid: str) -> dict:
    cur.execute(
        f"SELECT {CAMPOS} FROM plat.webhook w LEFT JOIN plat.usuario u ON u.id = w.criado_por "
        "WHERE w.id = %s::uuid",  # noqa: S608
        (wid,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "webhook_inexistente", "webhook inexistente")
    return r


@router.get("", response_model=WebhookPagina, openapi_extra=PRIV)
def listar(auth: Auth = autenticado("org.integracoes")):
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.webhook")
        total = cur.fetchone()["n"]
        cur.execute(f"SELECT {CAMPOS} FROM plat.webhook w "  # noqa: S608
                    "LEFT JOIN plat.usuario u ON u.id = w.criado_por ORDER BY lower(w.nome)")
        return {"total": total, "itens": [_webhook_json(r) for r in cur.fetchall()]}


@router.post("", response_model=WebhookSegredo, status_code=201, openapi_extra=PRIV)
def criar(dados: WebhookEntrada, request: Request, auth: Auth = autenticado("org.integracoes")):
    _url_ok(dados.url)
    segredo = assinatura.gerar_segredo()
    with db.db(auth.contexto()) as cur:
        _eventos_ok(cur, dados.eventos)
        cur.execute(
            "INSERT INTO plat.webhook(tenant_id, nome, url, eventos, segredo_cifrado, criado_por) "
            "VALUES (plat.tenant_atual(), %s, %s, %s, %s, plat.usuario_atual()) RETURNING id",
            (dados.nome.strip(), dados.url, dados.eventos,
             assinatura.cifrar(segredo, settings.PLAT_SECRET)),
        )
        wid = str(cur.fetchone()["id"])
        registrar_evento(cur, request, "webhooks/criar", "webhook", wid,
                         {"nome": dados.nome.strip(), "url": dados.url, "eventos": dados.eventos})
        r = _carregar(cur, wid)
    saida = _webhook_json(r)
    saida["segredo"] = segredo  # a única vez
    return saida


@router.get("/{id}", response_model=Webhook, openapi_extra=PRIV)
def ver(id: str, auth: Auth = autenticado("org.integracoes")):
    wid = uuid_ok(id, "webhook_inexistente", "webhook inexistente")
    with db.db(auth.contexto()) as cur:
        return _webhook_json(_carregar(cur, wid))


@router.patch("/{id}", response_model=Webhook, openapi_extra=PRIV)
def editar(id: str, dados: WebhookEditar, request: Request,
           auth: Auth = autenticado("org.integracoes")):
    wid = uuid_ok(id, "webhook_inexistente", "webhook inexistente")
    mudancas = dados.model_dump(exclude_none=True)
    if not mudancas:
        raise ErroAPI(422, "nada_para_mudar", "informe ao menos um campo (nome, url, eventos)")
    with db.db(auth.contexto()) as cur:
        atual = _carregar(cur, wid)
        if "url" in mudancas:
            _url_ok(mudancas["url"])
        if "eventos" in mudancas:
            _eventos_ok(cur, mudancas["eventos"])
        campos, params = [], []
        for campo in ("nome", "url", "eventos"):
            if campo in mudancas:
                valor = mudancas[campo]
                if campo == "nome":
                    valor = valor.strip()
                campos.append(f"{campo} = %s")
                params.append(valor)
        cur.execute(f"UPDATE plat.webhook SET {', '.join(campos)}, atualizado_em = now() "  # noqa: S608
                    "WHERE id = %s::uuid", (*params, wid))
        registrar_evento(cur, request, "webhooks/atualizar", "webhook", wid,
                         {"antes": {"nome": atual["nome"], "url": atual["url"],
                                    "eventos": list(atual["eventos"] or [])},
                          "depois": mudancas})
        return _webhook_json(_carregar(cur, wid))


@router.post("/{id}/rotacionar", response_model=WebhookSegredo, openapi_extra=PRIV)
def rotacionar(id: str, request: Request, auth: Auth = autenticado("org.integracoes")):
    """Segredo novo; o antigo deixa de assinar na PRÓXIMA entrega (não há janela de dupla assinatura:
    quem coordenar a troca no receptor, coordena — o aviso é este)."""
    wid = uuid_ok(id, "webhook_inexistente", "webhook inexistente")
    segredo = assinatura.gerar_segredo()
    with db.db(auth.contexto()) as cur:
        atual = _carregar(cur, wid)
        cur.execute("UPDATE plat.webhook SET segredo_cifrado = %s, atualizado_em = now() "
                    "WHERE id = %s::uuid",
                    (assinatura.cifrar(segredo, settings.PLAT_SECRET), wid))
        registrar_evento(cur, request, "webhooks/rotacionar", "webhook", wid,
                         {"nome": atual["nome"]})
        r = _carregar(cur, wid)
    saida = _webhook_json(r)
    saida["segredo"] = segredo  # a única vez
    return saida


@router.delete("/{id}", status_code=204, openapi_extra=PRIV)
def apagar(id: str, request: Request, auth: Auth = autenticado("org.integracoes")):
    wid = uuid_ok(id, "webhook_inexistente", "webhook inexistente")
    with db.db(auth.contexto()) as cur:
        atual = _carregar(cur, wid)
        cur.execute("DELETE FROM plat.webhook WHERE id = %s::uuid", (wid,))  # entregas cascadam
        registrar_evento(cur, request, "webhooks/apagar", "webhook", wid,
                         {"nome": atual["nome"], "url": atual["url"]})


@router.post("/{id}/reativar", response_model=Webhook, openapi_extra=PRIV)
def reativar(id: str, request: Request, auth: Auth = autenticado("org.integracoes")):
    """Desfaz a desativação (automática ou não): limpa o motivo, zera a conta de falhas e volta a
    receber despachos. Nada reteste a URL aqui — quem reativa afirma que o receptor foi corrigido."""
    wid = uuid_ok(id, "webhook_inexistente", "webhook inexistente")
    with db.db(auth.contexto()) as cur:
        atual = _carregar(cur, wid)
        if atual["ativo"]:
            raise ErroAPI(409, "webhook_ativo", "o webhook já está ativo")
        cur.execute("UPDATE plat.webhook SET ativo = true, falhas_consecutivas = 0, "
                    "desativada_em = NULL, desativada_motivo = NULL, atualizado_em = now() "
                    "WHERE id = %s::uuid", (wid,))
        registrar_evento(cur, request, "webhooks/reativar", "webhook", wid, {"nome": atual["nome"]})
        return _webhook_json(_carregar(cur, wid))


@router.get("/{id}/entregas", response_model=EntregaPagina, openapi_extra=PRIV)
def entregas(id: str, estado: str | None = None, limite: int = ENTREGA_LIMITE_PADRAO,
             auth: Auth = autenticado("org.integracoes")):
    """Log de entregas do webhook (RLS do inquilino; `plat.webhook_entrega` é SELECT/UPDATE a plat_app,
    INSERT só pelo gatilho de despacho)."""
    wid = uuid_ok(id, "webhook_inexistente", "webhook inexistente")
    if limite < 1 or limite > ENTREGA_LIMITE_MAX:
        raise ErroAPI(422, "limite_invalido", f"limite entre 1 e {ENTREGA_LIMITE_MAX}")
    onde, params = ["webhook_id = %s::uuid"], [wid]
    if estado is not None:
        if estado not in ESTADOS_ENTREGA:
            raise ErroAPI(422, "estado_invalido",
                          f"estado entre {', '.join(ESTADOS_ENTREGA)}")
        onde.append("estado = %s")
        params.append(estado)
    filtro = " AND ".join(onde)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, wid)  # 404 se o webhook não é do inquilino
        cur.execute(f"SELECT count(*) AS n FROM plat.webhook_entrega WHERE {filtro}", params)  # noqa: S608
        total = cur.fetchone()["n"]
        cur.execute(f"SELECT * FROM plat.webhook_entrega WHERE {filtro} "  # noqa: S608
                    "ORDER BY criado_em DESC LIMIT %s", (*params, limite))
        return {"total": total, "itens": [_entrega_json(r) for r in cur.fetchall()]}


@router.post("/{id}/entregas/{entrega_id}/reenviar", response_model=Entrega, openapi_extra=PRIV)
def reenviar(id: str, entrega_id: str, request: Request,
             auth: Auth = autenticado("org.integracoes")):
    """Reenvio manual: a MESMA entrega volta a 'pendente' com o MESMO payload e o MESMO `webhook-id`
    (idempotência no receptor) e um job novo entra na fila (tentativas recomeçam no job; `tentativas`
    da entrega segue acumulando como histórico)."""
    wid = uuid_ok(id, "webhook_inexistente", "webhook inexistente")
    eid = uuid_ok(entrega_id, "entrega_inexistente", "entrega inexistente")
    with db.db(auth.contexto()) as cur:
        _carregar(cur, wid)
        cur.execute("SELECT id, estado, payload FROM plat.webhook_entrega "
                    "WHERE id = %s::uuid AND webhook_id = %s::uuid", (eid, wid))
        entrega = cur.fetchone()
        if entrega is None:
            raise ErroAPI(404, "entrega_inexistente", "entrega inexistente")
        if entrega["estado"] == "pendente":
            raise ErroAPI(409, "entrega_pendente",
                          "a entrega já está pendente; aguarde o fim das tentativas")
        cur.execute("UPDATE plat.webhook_entrega SET estado = 'pendente', reenvios = reenvios + 1 "
                    "WHERE id = %s::uuid", (eid,))
        try:
            sistema.enfileirar(auth.contexto().tenant_id, "webhooks.entregar", {"entrega_id": eid},
                               usuario_id=auth.usuario_id, prioridade=2)
        except ValidationError as e:  # nunca deve ocorrer: payload é o mesmo já entregue uma vez
            raise ErroAPI(500, "reenvio_invalido", "parâmetros do reenvio inválidos") from e
        registrar_evento(cur, request, "webhooks/reenvio", "webhook", wid,
                         {"entrega_id": eid, "estado_anterior": entrega["estado"]})
        cur.execute("SELECT * FROM plat.webhook_entrega WHERE id = %s::uuid", (eid,))
        return _entrega_json(cur.fetchone())
