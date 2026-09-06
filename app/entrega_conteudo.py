"""Entrega segura de byte enviado pelo cliente (item L7-03-b-antivirus-anexos, 2ª metade: "o conteúdo é servido
com tipo seguro e com cabeçalho que força download"; docs/SEGURANCA.md §8.6).

Medido pelo adversário independente (handoff T3, achado 23, cadeia): `GET /api/arquivos/{sha256}` devolvia o
conteúdo com `media_type=r["content_type"]` — o MESMO `Content-Type` que o remetente escolheu no envio — sem
`Content-Disposition`. Um arquivo enviado como `text/html` voltava renderizando como HTML na própria origem da
aplicação (a sessão do usuário vale ali), e `X-Content-Type-Options: nosniff` não resolve esse caso: o tipo
declarado É `text/html`, não há adivinhação para desligar.

As três regras desta camada, aplicadas juntas em toda rota que devolve byte que veio de fora:

1. **tipo de mídia por lista fechada**: só os tipos do vocabulário da instalação (`app/objetos.EXTENSOES`)
   voltam como foram declarados; QUALQUER outro — inclusive `text/html`, `application/xhtml+xml`,
   `image/svg+xml` e as variações de JavaScript — é rebaixado para `application/octet-stream`. Lista fechada,
   não lista de proibidos: tipo novo inventado pelo remetente já cai no rebaixamento sem ninguém lembrar de
   acrescentá-lo a uma lista de perigosos.
2. **`Content-Disposition: attachment`** com nome saneado: o navegador salva o arquivo em vez de renderizar.
   O nome vai duas vezes, como manda a RFC 6266: `filename=` só com ASCII (aspas e barra invertida fora) para
   cliente antigo, e `filename*=UTF-8''...` (RFC 5987) com o nome por extenso.
3. **`X-Content-Type-Options: nosniff`**: fecha a adivinhação de tipo que sobraria no cliente.

Onde NÃO se força download, e por quê: a miniatura de item (`app/catalogo/miniatura.py::entregar`) é um PNG
REDESENHADO pelo Pillow (nunca os bytes do cliente) e é servida dentro de `<img>` na aplicação — forçar
download quebraria a tela sem fechar risco nenhum; ali entra só o `nosniff`."""

from __future__ import annotations

import re
from urllib.parse import quote

from app.objetos import EXTENSOES

TIPO_GENERICO = "application/octet-stream"
NOME_MAX = 80  # nome de arquivo sugerido; o conteúdo real nunca depende dele
_INSEGURO = re.compile(r'[\x00-\x1f\x7f"\\/:*?<>|]')


def tipo_de_entrega(content_type: str | None) -> str:
    """Tipo de mídia com que o conteúdo do cliente pode voltar: só o vocabulário fechado da instalação; o
    resto vira `application/octet-stream` (nunca `text/html`, `application/xhtml+xml`, `image/svg+xml` ou
    JavaScript a partir de byte enviado por alguém)."""
    tipo = (content_type or "").split(";")[0].strip().lower()
    return tipo if tipo in EXTENSOES else TIPO_GENERICO


def nome_saneado(nome: str, extensao: str = "") -> str:
    """Nome de arquivo sugerido, sem caractere de controle, aspas, barra ou separador de caminho."""
    limpo = _INSEGURO.sub("_", nome).strip(" .") or "arquivo"
    if extensao:
        limpo = f"{limpo}.{_INSEGURO.sub('_', extensao).strip(' .')}"
    return limpo[:NOME_MAX]


def cabecalhos_de_anexo(nome: str, extras: dict[str, str] | None = None) -> dict[str, str]:
    """`Content-Disposition: attachment` (nas duas formas da RFC 6266) + `X-Content-Type-Options: nosniff`."""
    ascii_puro = nome.encode("ascii", "replace").decode("ascii").replace("?", "_")
    cabecalhos = {
        "Content-Disposition": f"attachment; filename=\"{ascii_puro}\"; filename*=UTF-8''{quote(nome)}",
        "X-Content-Type-Options": "nosniff",
    }
    cabecalhos.update(extras or {})
    return cabecalhos
