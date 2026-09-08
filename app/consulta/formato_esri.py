"""Negociação do parâmetro `f` do protocolo Esri (item L2-04-b).

Todo recurso do diretório de serviços responde ao mesmo contrato: `f=json` (padrão), `f=pjson`
(o mesmo JSON indentado, que é o que o navegador do técnico abre), `f=html` (a Esri serve a página
do "Services Directory"; aqui vai uma página simples, porque o que NÃO pode acontecer é 500 num
formato previsto pelo protocolo) e `callback=` (JSONP, como AGOL e visualizadores antigos pedem
quando não há CORS).

O nome da função de JSONP vem do cliente e é escrito DENTRO de um documento JavaScript: só passa
identificador simples (letras, dígitos, `_`, `$` e ponto de caminho tipo `janela.cb`). Qualquer
outra coisa é recusada com 400 — nunca ecoada, que seria injeção de script refletida."""

from __future__ import annotations

import html
import json
import re

from fastapi import Response

from app.erros import ErroAPI

FORMATOS = ("json", "pjson", "html")
# `f=image` é o segundo contrato do protocolo: nas operações que DESENHAM (export, legend), `f=json`
# devolve a descrição da imagem e `f=image` devolve os bytes dela. Não entra em `FORMATOS` porque não
# faz sentido em recurso de metadado — quem aceita passa `extras=("image",)` a `formato_de`.
FORMATO_IMAGEM = "image"
_CALLBACK_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*(\.[A-Za-z_$][A-Za-z0-9_$]*)*$")
_CALLBACK_MAX = 128


def formato_de(valor: str | None, extras: tuple[str, ...] = ()) -> str:
    """`f` normalizado. Ausente ou vazio = json (padrão do protocolo). Valor fora do vocabulário é
    400, não 500: o cliente pediu formato que não existe, e o erro é dele. `extras` acrescenta os
    formatos que SÓ aquela operação entende (hoje `image`, do export e da legenda do MapServer)."""
    aceitos = FORMATOS + tuple(extras)
    f = (valor or "json").strip().lower()
    if f not in aceitos:
        raise ErroAPI(400, "formato_nao_suportado", f"f={f} não é suportado; use {', '.join(aceitos)}")
    return f


def resposta_imagem(dados: bytes, tipo_conteudo: str) -> Response:
    """Bytes de imagem/PDF já codificados. `no-store` porque o desenho depende do token do caminho e
    dos parâmetros do pedido: nenhuma camada intermediária deve guardar a imagem de um inquilino."""
    return Response(dados, media_type=tipo_conteudo,
                    headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


def validar_callback(valor: str | None) -> str | None:
    if valor is None or valor == "":
        return None
    if len(valor) > _CALLBACK_MAX or not _CALLBACK_RE.match(valor):
        raise ErroAPI(400, "callback_invalido", "callback aceita só identificador JavaScript simples")
    return valor


def _pagina(dado: dict | list) -> str:
    corpo = html.escape(json.dumps(dado, ensure_ascii=False, indent=2, default=str))
    return (
        "<!doctype html><meta charset=\"utf-8\"><title>Diretório de serviços</title>"
        "<body style=\"font:14px system-ui;margin:1.5rem\">"
        "<h1 style=\"font-size:1.1rem\">Diretório de serviços</h1>"
        f"<pre style=\"white-space:pre-wrap\">{corpo}</pre></body>"
    )


def resposta_esri(dado: dict | list, f: str | None = None, callback: str | None = None) -> Response:
    """Serializa `dado` no formato pedido. JSONP vence `f` (é assim que a Esri se comporta: com
    `callback` presente o corpo é sempre JavaScript)."""
    formato = formato_de(f)
    cb = validar_callback(callback)
    if cb is not None:
        corpo = json.dumps(dado, ensure_ascii=False, default=str)
        return Response(f"{cb}({corpo});", media_type="text/javascript; charset=utf-8")
    if formato == "html":
        return Response(_pagina(dado), media_type="text/html; charset=utf-8")
    indent = 2 if formato == "pjson" else None
    corpo = json.dumps(dado, ensure_ascii=False, indent=indent, default=str)
    return Response(corpo, media_type="application/json")
