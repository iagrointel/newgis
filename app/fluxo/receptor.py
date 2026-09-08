"""Receptor de eventos do processo `plat-fluxo` (item L2-14-a-ingestao-de-fluxos): aplicação ASGI PRÓPRIA,
separada da API da plataforma, na porta `FLUXO_PORTA` (8155).

Por que separada da API: o caminho de um evento tem de ser uma conta de memória. O middleware da API grava
uma linha em `plat.log_acesso` por requisição, resolve sessão, aplica CSRF e monta o contrato de erro — tudo
certo para uma chamada humana e caro demais para dez mil eventos por segundo. Aqui só existe o que o evento
precisa: ler o corpo com teto, achar a fonte no registro em memória, aplicar teto/mapeamento/filtro e
enfileirar. A autenticação é a MESMA (token de serviço do L0-02-d, `app/fluxo/autenticacao.py`).

Rotas:
  POST /fluxo/{fonte_id}/eventos  — corpo no formato declarado na fonte (ou no `Content-Type`)
  WS   /fluxo/{fonte_id}/ws       — fonte `websocket_servidor`: um evento (ou lote) por quadro de texto
  GET  /saude                     — estado do processo e métrica POR FONTE (recebidos, aceitos,
                                    descartados por motivo, atraso); sem token devolve só o resumo do
                                    processo, com token do inquilino devolve as fontes dele

Nenhuma rota devolve dado de outro inquilino: a fonte é sempre procurada pelo inquilino DO TOKEN.
"""

from __future__ import annotations

import json
import logging

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from app import limites
from app.fluxo import autenticacao, entrada
from app.fluxo import formato as mod_formato
from app.fluxo.tipos import FORMATOS_POR_TIPO

log = logging.getLogger("plat.fluxo.receptor")

TIPO_CONTEUDO = {
    "application/json": "json",
    "application/geo+json": "geojson",
    "application/x-ndjson": "ndjson",
    "application/gpx+xml": "gpx",
    "text/csv": "csv",
}


def _erro(status: int, codigo: str, mensagem: str, extra: dict | None = None) -> JSONResponse:
    corpo = {"erro": codigo, "mensagem": mensagem}
    if extra:
        corpo.update(extra)
    return JSONResponse(corpo, status_code=status, headers={"Cache-Control": "no-store"})


def _formato_do_pedido(fonte, cabecalho: str | None, consulta: str | None) -> str:
    permitidos = FORMATOS_POR_TIPO.get(fonte.tipo, ("json",))
    if consulta:
        if consulta not in permitidos:
            raise mod_formato.ErroFormato(
                "formato_nao_suportado",
                f"a fonte do tipo {fonte.tipo} aceita: {', '.join(permitidos)}")
        return consulta
    if cabecalho:
        pelo_cabecalho = TIPO_CONTEUDO.get(cabecalho.split(";")[0].strip().lower())
        if pelo_cabecalho in permitidos:
            return pelo_cabecalho
    padrao = fonte.config.get("formato")
    return padrao if padrao in permitidos else permitidos[0]


def _ip(request) -> str | None:
    return request.client.host if request.client else None


def criar(registro, fila) -> Starlette:
    """`registro` = app.fluxo.fontes.Registro; `fila` = app.fluxo.fila.Fila. Injetados para o teste poder
    montar o receptor sem processo, sem porta e sem espera."""

    def _fonte_do_portador(portador, fonte_id: str):
        fonte = registro.obter(fonte_id)
        if fonte is None or fonte.tenant_id != portador.tenant_id:
            # fonte de OUTRO inquilino responde igual a fonte inexistente: 404, nunca 403 (não vaza
            # que o id existe). Cláusula do portão "token de A não escreve em fonte de B".
            raise autenticacao.ErroAutenticacao(404, "fonte_inexistente", "fonte de fluxo inexistente")
        return fonte

    async def receber(request):
        fonte_id = request.path_params["fonte_id"]
        try:
            portador = autenticacao.autenticar(request.headers.get("authorization"), ip=_ip(request))
            autenticacao.exigir_escrita(portador, fonte_id)
            fonte = _fonte_do_portador(portador, fonte_id)
        except autenticacao.ErroAutenticacao as e:
            return _erro(e.status, e.codigo, e.mensagem)
        except Exception:  # noqa: BLE001 — banco fora do ar na verificação do token
            log.exception("fluxo: falha ao autenticar no receptor")
            return _erro(503, "indisponivel", "verificação de token indisponível")

        declarado = request.headers.get("content-length")
        if declarado and declarado.isdigit() and int(declarado) > limites.FLUXO_CORPO_MAX_BYTES:
            return _erro(413, "corpo_grande_demais",
                         f"o corpo passa de {limites.FLUXO_CORPO_MAX_BYTES} bytes")
        corpo = b""
        async for pedaco in request.stream():
            corpo += pedaco
            if len(corpo) > limites.FLUXO_CORPO_MAX_BYTES:
                # corta a leitura em vez de aceitar o corpo inteiro: um remetente que mente no
                # Content-Length não consegue fazer o processo guardar mais que o teto
                return _erro(413, "corpo_grande_demais",
                             f"o corpo passa de {limites.FLUXO_CORPO_MAX_BYTES} bytes")
        try:
            fmt = _formato_do_pedido(fonte, request.headers.get("content-type"),
                                     request.query_params.get("formato"))
            registros = mod_formato.decodificar(corpo, fmt)
        except mod_formato.ErroFormato as e:
            fila.conta(fonte.id).somar_motivo(e.motivo)
            status = 413 if e.motivo in ("corpo_grande_demais", "lote_grande_demais") else 422
            return _erro(status, e.motivo, e.detalhe)

        resumo = entrada.ingerir(fonte, registros, fila)
        status = 202 if resumo["aceitos"] or resumo["em_buffer"] else 200
        return JSONResponse(resumo, status_code=status, headers={"Cache-Control": "no-store"})

    async def websocket(ws: WebSocket):
        fonte_id = ws.path_params["fonte_id"]
        try:
            cabecalho = ws.headers.get("authorization")
            if not cabecalho:
                # navegador não manda cabeçalho no WebSocket: o token pode vir na consulta, e é por isso
                # que ele nunca aparece em registro de acesso deste processo (não há registro por pedido)
                valor = ws.query_params.get("token")
                cabecalho = f"Bearer {valor}" if valor else None
            portador = autenticacao.autenticar(cabecalho, ip=ws.client.host if ws.client else None)
            autenticacao.exigir_escrita(portador, fonte_id)
            fonte = _fonte_do_portador(portador, fonte_id)
        except autenticacao.ErroAutenticacao as e:
            await ws.close(code=4401 if e.status == 401 else 4403 if e.status == 403 else 4404)
            return
        if fonte.tipo != "websocket_servidor":
            await ws.close(code=4400)
            return
        await ws.accept()
        try:
            while True:
                bruto = await ws.receive_text()
                if len(bruto.encode("utf-8")) > limites.FLUXO_CORPO_MAX_BYTES:
                    await ws.send_text(json.dumps({"erro": "corpo_grande_demais"}))
                    continue
                # a fonte pode ter sido pausada/editada entre um quadro e outro: relê do registro
                atual = registro.obter(fonte_id) or fonte
                try:
                    fmt = atual.config.get("formato") or "json"
                    registros = mod_formato.decodificar(bruto.encode("utf-8"), fmt)
                except mod_formato.ErroFormato as e:
                    fila.conta(atual.id).somar_motivo(e.motivo)
                    await ws.send_text(json.dumps({"erro": e.motivo}))
                    continue
                resumo = entrada.ingerir(atual, registros, fila)
                await ws.send_text(json.dumps(resumo))
        except WebSocketDisconnect:
            return

    async def saude(request):
        corpo = {
            "processo": "plat-fluxo",
            "fontes": len(registro.todas()),
            "fila": fila.tamanho(),
            "gravados": fila.gravados,
            "lotes": fila.lotes,
            "erros_de_escrita": fila.erros_de_escrita,
            "registro_carregado_em": registro.carregado_em,
            "registro_erro": registro.erro_da_carga,
        }
        cabecalho = request.headers.get("authorization")
        if cabecalho:
            try:
                portador = autenticacao.autenticar(cabecalho, ip=_ip(request))
            except autenticacao.ErroAutenticacao as e:
                return _erro(e.status, e.codigo, e.mensagem)
            corpo["por_fonte"] = {
                f.id: {"nome": f.nome, "tipo": f.tipo, "estado": f.estado,
                       "buffer": len(f.buffer), **fila.conta(f.id).instantaneo()}
                for f in registro.todas() if f.tenant_id == portador.tenant_id
            }
        return JSONResponse(corpo, headers={"Cache-Control": "no-store"})

    return Starlette(routes=[
        Route("/fluxo/{fonte_id}/eventos", receber, methods=["POST"]),
        WebSocketRoute("/fluxo/{fonte_id}/ws", websocket),
        Route("/saude", saude, methods=["GET"]),
    ])
