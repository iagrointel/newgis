"""Rotas de dados do documento de painel (item L2-06-a-modelo-painel-fontes): uma por contexto de leitura,
as duas com o MESMO contrato de corpo/resposta — `{"pedidos": {chave: {...}}, "filtro_execucao": {...}}` →
`{"resultados": {chave: {...}}}` (`app.paineis.dados.executar_pedidos`), sempre UM POST por FONTE (nunca por
elemento — o cliente agrupa antes de chamar, ver `web/js/paineis/painel.js`):

* `POST /api/itens/{item_id}/paineis/fontes/{fonte_id}/dados` — sessão/token com RLS normal (o mesmo que
  `GET /api/itens/{id}` já usa: `item_ou_404` só devolve o painel se o inquilino do contexto o vê).
* `POST /api/compartilhado/{token}/paineis/{item_id}/fontes/{fonte_id}/dados` — contexto ANÔNIMO do link
  (ADR 0004 seção 6; `rotas_compartilhamento.resolver_link`): a camada da fonte NÃO precisa estar em
  `itens_incluidos` do link — `plat.painel_camadas_resolver` (migração `20260906T2145_documento_painel.sql`)
  devolve só os metadados das camadas que o PRÓPRIO painel referencia, do MESMO inquilino do link, nunca por
  id pedido pelo cliente. É esta função, não a lista de itens do link, que fecha o vazamento entre
  inquilinos (cláusula do portão: "painel de A por link não vaza dado de B")."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import documento
from app.catalogo.comum import item_ou_404, uuid_ok
from app.catalogo.rotas_compartilhamento import resolver_link
from app.erros import ErroAPI
from app.paineis.dados import executar_pedidos

router = APIRouter(tags=["paineis"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
PUBLICO = {"x-auth": "-", "x-privilegio": "publico"}


def _corpo_painel(dados: dict) -> dict:
    migrado, _mudou, _de, _para = documento.migrar_para_leitura("painel", dados)
    corpo = migrado.get("corpo") if isinstance(migrado, dict) else None
    return corpo if isinstance(corpo, dict) else {}


def _fonte_do_corpo(corpo: dict, fonte_id: str) -> dict:
    for f in corpo.get("fontes") or []:
        if isinstance(f, dict) and f.get("id") == fonte_id:
            return f
    raise ErroAPI(404, "fonte_inexistente", "fonte inexistente neste painel")


class PedidoDados:
    """Corpo cru validado à mão (não Pydantic): `pedidos` é um objeto arbitrário chave→pedido — o
    schema de CADA pedido é decidido pelo tipo de elemento em `app.paineis.dados`, não pela rota."""


def _validar_corpo_requisicao(corpo: dict) -> tuple[dict, dict]:
    if not isinstance(corpo, dict):
        raise ErroAPI(422, "corpo_invalido", "corpo da requisição precisa ser um objeto")
    pedidos = corpo.get("pedidos")
    if not isinstance(pedidos, dict) or not pedidos:
        raise ErroAPI(422, "pedidos_vazios", "informe ao menos um pedido em 'pedidos'")
    filtro_execucao = corpo.get("filtro_execucao") or {}
    if not isinstance(filtro_execucao, dict):
        raise ErroAPI(422, "filtro_execucao_invalido", "'filtro_execucao' precisa ser um objeto")
    return pedidos, filtro_execucao


def _schema_tabela_da_camada(item_camada: dict) -> tuple[str, str]:
    dados = item_camada.get("dados") or {}
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if item_camada.get("tipo") not in ("camada_vetorial",) or not schema or not tabela:
        raise ErroAPI(404, "camada_nao_encontrada", "fonte não aponta para uma camada vetorial válida")
    return schema, tabela


@router.post("/api/itens/{item_id}/paineis/fontes/{fonte_id}/dados", openapi_extra=LER)
def painel_dados(
    item_id: str, fonte_id: str, corpo: dict, request: Request,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    iid, fid = uuid_ok(item_id), fonte_id
    pedidos, filtro_execucao = _validar_corpo_requisicao(corpo)
    with db.db(auth.contexto()) as cur:
        painel = item_ou_404(cur, iid)
        if painel["tipo"] != "painel":
            raise ErroAPI(404, "item_nao_e_painel", "item não é um documento de painel")
        painel_corpo = _corpo_painel(painel["dados"] or {})
        fonte = _fonte_do_corpo(painel_corpo, fid)
        ref = ((fonte.get("camada") or {}).get("ref"))
        if not ref:
            raise ErroAPI(422, "fonte_sem_camada", "fonte sem camada de referência")
        camada = item_ou_404(cur, uuid_ok(ref, "camada_inexistente", "camada da fonte inexistente"))
        schema, tabela = _schema_tabela_da_camada(camada)
        resultados = executar_pedidos(cur, schema, tabela, fonte, pedidos, filtro_execucao)
    return {"resultados": resultados}


@router.post("/api/compartilhado/{token}/paineis/{item_id}/fontes/{fonte_id}/dados", openapi_extra=PUBLICO)
def painel_dados_compartilhado(token: str, item_id: str, fonte_id: str, corpo: dict, request: Request):
    iid, fid = uuid_ok(item_id), fonte_id
    pedidos, filtro_execucao = _validar_corpo_requisicao(corpo)
    with db.db() as cur:
        link = resolver_link(cur, token, request)
        if iid not in link["itens"]:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
        painel = item_ou_404(cur, iid)
        if painel["tipo"] != "painel":
            raise ErroAPI(404, "item_nao_e_painel", "item não é um documento de painel")
        painel_corpo = _corpo_painel(painel["dados"] or {})
        fonte = _fonte_do_corpo(painel_corpo, fid)
        ref = ((fonte.get("camada") or {}).get("ref"))
        if not ref:
            raise ErroAPI(422, "fonte_sem_camada", "fonte sem camada de referência")
        # resolve a camada por FUNÇÃO SECURITY DEFINER que só devolve o que o PRÓPRIO painel referencia,
        # do mesmo inquilino do link — nunca por id livre pedido pelo cliente (ver docstring do módulo).
        cur.execute("SELECT id, tipo, titulo, dados FROM plat.painel_camadas_resolver(%s::uuid)", (iid,))
        camadas = {str(r["id"]): r for r in cur.fetchall()}
        camada = camadas.get(str(uuid_ok(ref, "camada_inexistente", "camada da fonte inexistente")))
        if camada is None:
            raise ErroAPI(404, "camada_nao_encontrada", "fonte não aponta para uma camada visível deste link")
        schema, tabela = _schema_tabela_da_camada(camada)
        resultados = executar_pedidos(cur, schema, tabela, fonte, pedidos, filtro_execucao)
    return {"resultados": resultados}
