"""Narrativa por blocos (item L5-04-a-blocos-de-conteudo): o que o SERVIDOR confere sobre `dados.corpo.nos` de um
item `narrativa` na hora de PUBLICAR (`app/catalogo/publicacao.py`). O editor (paleta `web/js/editor/
paleta_narrativa.js`) já recusa valor fora do esquema campo a campo; aqui fica a regra que o esquema não
expressa e que tem de valer mesmo para quem grava pela API: imagem sem texto alternativo não publica
(acessibilidade, WCAG 1.1.1), endereço de mídia/embed fora do próprio servidor só por https, e bloco de tipo
desconhecido não publica (o leitor não saberia desenhá-lo).

Também extrai as referências a itens do catálogo (mapa do bloco `mapa`, app/painel do bloco `aplicativo`) para
`plat.item_relacao` — é por elas que `camadas_citadas` do L5-14 chega às camadas que o token da publicação pode
ler (narrativa → mapa → camada)."""

from __future__ import annotations

import re
import uuid

TIPOS_BLOCO = {"capa", "texto", "imagem", "video", "audio", "mapa", "tabela", "botao", "separador", "incorporar",
               "aplicativo"}
_PROPRIA = re.compile(r"^/(?!/)[A-Za-z0-9._~!$&()*+,;=:@%/-]*$")
_HTTPS = re.compile(r"^https://[^\s<>\"']+$")


def blocos(dados: dict | None) -> list[dict]:
    corpo = (dados or {}).get("corpo") or {}
    nos = corpo.get("nos") or []
    return [n for n in nos if isinstance(n, dict)]


def _url_ok(valor, *, so_propria: bool = False) -> bool:
    if not isinstance(valor, str) or not valor:
        return False
    if _PROPRIA.match(valor):
        return True
    return (not so_propria) and bool(_HTTPS.match(valor))


def problemas_para_publicar(dados: dict | None) -> list[dict]:
    """[{bloco, tipo, campo, erro}] — vazio = pode publicar. Mensagens em português, prontas para a tela."""
    saida: list[dict] = []

    def erro(no, campo, mensagem):
        saida.append({"bloco": no.get("id"), "tipo": no.get("tipo"), "campo": campo, "erro": mensagem})

    for no in blocos(dados):
        tipo = no.get("tipo")
        p = no.get("propriedades") or {}
        if tipo not in TIPOS_BLOCO:
            erro(no, "tipo", f"bloco de tipo desconhecido: {tipo!r}")
            continue
        if tipo == "imagem":
            if not _url_ok(p.get("url")):
                erro(no, "url", "imagem sem endereço válido (caminho do próprio servidor ou https)")
            if not str(p.get("alternativo") or "").strip():
                erro(no, "alternativo", "imagem sem texto alternativo: descreva a imagem para quem não a vê")
        elif tipo == "capa":
            if not str(p.get("titulo") or "").strip():
                erro(no, "titulo", "capa sem título")
            if p.get("imagem"):
                if not _url_ok(p.get("imagem")):
                    erro(no, "imagem", "imagem de capa com endereço inválido")
                if not str(p.get("alternativo") or "").strip():
                    erro(no, "alternativo", "imagem de capa sem texto alternativo")
        elif tipo == "texto":
            if not str(p.get("markdown") or "").strip():
                erro(no, "markdown", "bloco de texto vazio")
        elif tipo in ("video", "audio"):
            if not _url_ok(p.get("url"), so_propria=(tipo == "audio")):
                erro(no, "url", f"{tipo} sem endereço válido")
        elif tipo == "incorporar":
            if not (isinstance(p.get("url"), str) and _HTTPS.match(p["url"])):
                erro(no, "url", "incorporar só aceita endereço https")
            if not str(p.get("titulo") or "").strip():
                erro(no, "titulo", "quadro incorporado sem título acessível")
        elif tipo == "botao":
            if not _url_ok(p.get("url")):
                erro(no, "url", "botão sem endereço válido")
            if not str(p.get("rotulo") or "").strip():
                erro(no, "rotulo", "botão sem rótulo")
        elif tipo == "aplicativo":
            if not _uuid(p.get("item_id")):
                erro(no, "item_id", "bloco de aplicativo sem item do catálogo")
        elif tipo == "mapa":
            vista = p.get("vista")
            if vista is not None and not _vista_ok(vista):
                erro(no, "vista", "vista salva incompleta (bbox, centro, zoom e proporção)")
    return saida


def _uuid(v) -> str | None:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError, AttributeError):
        return None


def _vista_ok(vista) -> bool:
    if not isinstance(vista, dict):
        return False
    bbox = vista.get("bbox")
    centro = vista.get("centro")
    try:
        ok = (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox)
              and bbox[0] < bbox[2] and bbox[1] < bbox[3]
              and isinstance(centro, list) and len(centro) == 2
              and 0 <= float(vista.get("zoom")) <= 24 and 0.2 <= float(vista.get("proporcao")) <= 3)
    except (TypeError, ValueError):
        return False
    return bool(ok)


def relacoes(dados: dict) -> list[tuple[str, str, int | None]]:
    """(uuid, tipo_da_relação, ordem) para `app/catalogo/relacoes.py`: mapa citado pelo bloco `mapa`, app/painel
    pelo bloco `aplicativo`. A ordem é a posição do bloco na narrativa."""
    saida: list[tuple[str, str, int | None]] = []
    vistos: set[str] = set()
    for i, no in enumerate(blocos(dados)):
        p = no.get("propriedades") or {}
        tipo = no.get("tipo")
        if tipo == "mapa":
            alvo = _uuid(p.get("mapa_id"))
        elif tipo == "aplicativo":
            alvo = _uuid(p.get("item_id"))
        else:
            alvo = None
        if alvo and alvo not in vistos:
            vistos.add(alvo)
            saida.append((alvo, "mapa_de_narrativa" if tipo == "mapa" else "app_de_narrativa", i))
    return saida
