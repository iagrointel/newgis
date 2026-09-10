"""Rota do fluxo de eventos de camada (item L2-06-d-atualizacao-viva-sse).

`GET /api/eventos/camadas?camadas=<uuid>,<uuid>` — Server-Sent Events, autenticado, filtrado por inquilino e
pela lista de camadas assinadas. O caminho é `/api/eventos/camadas` e não `/api/eventos` porque este último
já é a listagem do log de eventos de domínio (L0-02); são coisas diferentes e não se confundem na URL.

Ordem das checagens (importa para o teste cruzado A→B não ficar pendurado num fluxo infinito): TUDO que pode
recusar acontece ANTES de o `StreamingResponse` começar — camada inexistente ou de outro inquilino é 404 na
hora, cota estourada é 429 na hora, SSE desligado por configuração é 503 na hora. Só depois disso a resposta
vira fluxo.

Desligar o SSE (`PLAT_SSE_LIGADO=false`) é um interruptor de operação para o caso do proxy à frente não
sustentar conexão longa: a rota passa a responder 503 `sse_desligado` e o navegador cai sozinho no
intervalo de atualização configurado em cada fonte do painel (`web/js/paineis/render.js`).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import uuid_ok
from app.erros import ErroAPI
from app.vivo import eventos

router = APIRouter(tags=["vivo"])
XV = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}


def _camadas_pedidas(bruto: str) -> list[str]:
    ids = [p.strip() for p in (bruto or "").split(",") if p.strip()]
    if not ids:
        raise ErroAPI(400, "camadas_vazias", "informe ao menos uma camada em 'camadas'")
    if len(ids) > eventos.CAMADAS_MAX:
        raise ErroAPI(422, "camadas_demais",
                      f"máximo de {eventos.CAMADAS_MAX} camadas por conexão de eventos")
    vistos: list[str] = []
    for i in ids:
        u = str(uuid_ok(i, "camada_invalida", "identificador de camada inválido"))
        if u not in vistos:
            vistos.append(u)
    return vistos


def ultimo_id_do_cabecalho(cabecalho: str | None) -> int | None:
    """`Last-Event-ID` do navegador. Só dígito vale; qualquer outra coisa (cabeçalho forjado, vazio,
    negativo, texto de injeção) é tratada como ausente e o fluxo começa do presente — nunca erro 500, que
    é o que a refutação do item procura ao mandar um Last-Event-ID inválido.

    O `isascii()` não é enfeite: `str.isdigit()` aceita dígito de outro sistema de escrita (o arábico-índico
    "٣" passa e `int()` o converte em 3), e um id que o servidor nunca emitiu não deve virar ponto de
    partida de reenvio."""
    if not cabecalho or not cabecalho.isascii() or not cabecalho.isdigit():
        return None
    return int(cabecalho)


def _resolver_e_observar(ctx, camadas: list[str]) -> None:
    """Sob RLS: cada camada tem de existir, ser deste inquilino e ser vetorial — senão 404 (nunca 403, que
    revelaria a existência de camada alheia). Já aproveita e instala o gatilho de notificação na tabela
    física (função idempotente e sem DDL quando o gatilho já está lá)."""
    with db.db(ctx) as cur:
        cur.execute(
            "SELECT id, tipo FROM plat.item WHERE id = ANY(%s::uuid[]) AND apagado_em IS NULL",
            (list(camadas),),
        )
        achadas = {str(r["id"]): r["tipo"] for r in cur.fetchall()}
        for c in camadas:
            if achadas.get(c) != "camada_vetorial":
                raise ErroAPI(404, "camada_inexistente", "camada inexistente")
            cur.execute("SELECT plat.camada_observar(%s::uuid) AS ok", (c,))


@router.get("/api/eventos/camadas",
            responses={200: {"content": {"text/event-stream": {}}}}, openapi_extra=XV)
async def eventos_de_camadas(
    request: Request,
    camadas: str = Query(..., description="ids de camada separados por vírgula"),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Fluxo SSE: `pronto` com a versão corrente de cada camada, depois um `camada` por comando de edição
    confirmado; `Last-Event-ID` reenvia o que passou na janela de reconexão."""
    from app.settings import settings

    if not settings.PLAT_SSE_LIGADO:
        raise ErroAPI(503, "sse_desligado",
                      "fluxo de eventos desligado nesta instalação; use o intervalo de atualização")
    ids = _camadas_pedidas(camadas)
    ctx = auth.contexto()
    _resolver_e_observar(ctx, ids)
    eventos.reservar(auth.tenant_id, auth.usuario_id)
    ultimo_id = ultimo_id_do_cabecalho(request.headers.get("Last-Event-ID"))
    return StreamingResponse(
        eventos.gerar(ctx, auth.tenant_id, auth.usuario_id, ids, ultimo_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
