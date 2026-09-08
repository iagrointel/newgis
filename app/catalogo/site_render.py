"""Renderização no servidor das páginas de site (item L5-20-sites-paginas-publicas; L5_CONCEITO D24).

Entra um documento de site (`app/catalogo/site.py`) e o contexto do inquilino; sai HTML COMPLETO, com o texto
dentro do HTML. A regra do item é literal: `curl` sem navegador tem de ler o conteúdo. Por isso nenhum cartão
depende de JavaScript para mostrar o que diz — a galeria e a busca são formulários `GET` que o servidor
responde já filtrado, o mapa e o aplicativo são `<iframe>` com link equivalente ao lado, e a estatística é
número contado no banco na hora do pedido.

Sem motor de template e sem dependência nova: `html.escape` + f-string, o mesmo caminho de
`app/catalogo/publicacao.py::exportacao_estatica`. Todo texto vindo do documento é escapado; nada do que o
autor do site escreve é interpretado como HTML.

O que a página só consulta pelas funções `plat.site_*` (que filtram `acesso = 'publico'`): galeria, busca,
estatística e os cartões que citam item por uuid. Um cartão que aponta para item privado não mostra o item —
mostra a frase de que o conteúdo não está compartilhado com todos. É esta a defesa contra vazamento por id.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from app import limites
from app.catalogo.site import CARTOES, FAMILIAS_ROTULO

CSS = "/static/estilo/site.css"


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


@dataclass
class Contexto:
    """Tudo o que a renderização precisa saber do inquilino e do pedido — nada é lido de variável global."""

    cur: object
    tenant_id: int
    tenant_slug: str
    tenant_nome: str
    cor: str
    logo: str | None
    indexavel: bool
    parametros: dict = field(default_factory=dict)


# ---------------------------------------------------------------- leitura do documento
def _prop(no: dict) -> dict:
    p = no.get("propriedades")
    return p if isinstance(p, dict) else {}


def _nos(corpo: dict) -> list[dict]:
    nos = (corpo or {}).get("nos")
    return [n for n in nos if isinstance(n, dict)] if isinstance(nos, list) else []


def _do_tipo(nos: list[dict], tipo: str, pai=None) -> list[dict]:
    return [n for n in nos if n.get("tipo") == tipo and (n.get("pai") or None) == pai]


def paginas(corpo: dict) -> list[dict]:
    lista = _do_tipo(_nos(corpo), "pagina")
    return sorted(lista, key=lambda n: (int(_prop(n).get("ordem") or 0), lista.index(n)))


def pagina_por_caminho(corpo: dict, caminho: str) -> dict | None:
    lista = paginas(corpo)
    if not lista:
        return None
    if not caminho:
        inicial = [n for n in lista if _prop(n).get("inicial")]
        return inicial[0] if inicial else lista[0]
    for n in lista:
        if _prop(n).get("caminho") == caminho:
            return n
    return None


# ---------------------------------------------------------------- cor do tema
def _luminancia(cor: str) -> float:
    """Luminância relativa (WCAG 2.1, 1.4.3) da cor do inquilino, para escolher texto claro ou escuro sobre
    ela. Sem isto, um inquilino de cor clara ficaria com texto branco sobre fundo claro — contraste reprovado."""
    try:
        r, g, b = (int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except (ValueError, IndexError):
        return 0.0
    canais = []
    for c in (r, g, b):
        canais.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def cor_do_texto(cor: str) -> str:
    """Preto ou branco sobre a cor do inquilino, o que der mais contraste (razão contra branco x contra preto)."""
    lum = _luminancia(cor)
    contraste_branco = 1.05 / (lum + 0.05)
    contraste_preto = (lum + 0.05) / 0.05
    return "#ffffff" if contraste_branco >= contraste_preto else "#111111"


# ---------------------------------------------------------------- cartões
def _paragrafos(texto: str) -> str:
    blocos = [b.strip() for b in str(texto or "").split("\n\n") if b.strip()]
    return "".join(f"<p>{esc(b)}</p>" for b in blocos) or "<p></p>"


def _titulo_cartao(p: dict, nivel: str = "h3") -> str:
    titulo = p.get("titulo")
    return f"<{nivel}>{esc(titulo)}</{nivel}>" if isinstance(titulo, str) and titulo.strip() else ""


def _altura(p: dict) -> int:
    try:
        v = int(p.get("altura") or 420)
    except (TypeError, ValueError):
        v = 420
    return max(limites.SITE_INCORPORADO_ALTURA_MIN, min(limites.SITE_INCORPORADO_ALTURA_MAX, v))


def _item_publico(ctx: Contexto, item_id: str) -> dict | None:
    ctx.cur.execute("SELECT * FROM plat.site_item_publico(%s, %s::uuid)", (ctx.tenant_id, item_id))
    return ctx.cur.fetchone()


def _publicacao_do_item(ctx: Contexto, item_id: str) -> str | None:
    """Slug da publicação `/p/<inquilino>/<slug>` do item, se ele estiver publicado. Vai por função
    SECURITY DEFINER: a página do site é anônima e a RLS de `item_publicacao` exige contexto de sessão — sem
    ela o cartão de mapa ficava mudo mesmo com o aplicativo publicado (achado ao rodar o teste)."""
    ctx.cur.execute("SELECT plat.site_publicacao_slug(%s, %s::uuid) AS slug", (ctx.tenant_id, item_id))
    r = ctx.cur.fetchone()
    return r["slug"] if r and r["slug"] else None


def _sem_acesso(mensagem: str) -> str:
    return f'<p class="site-indisponivel">{esc(mensagem)}</p>'


def cartao_texto(ctx: Contexto, no: dict) -> str:
    p = _prop(no)
    return f'<div class="cartao cartao-texto">{_titulo_cartao(p)}{_paragrafos(p.get("texto"))}</div>'


def cartao_imagem(ctx: Contexto, no: dict) -> str:
    p = _prop(no)
    legenda = p.get("legenda")
    fig_legenda = f"<figcaption>{esc(legenda)}</figcaption>" if isinstance(legenda, str) and legenda.strip() else ""
    return (f'<figure class="cartao cartao-imagem"><img src="{esc(p.get("url"))}" alt="{esc(p.get("alternativo"))}"'
            f' loading="lazy">{fig_legenda}</figure>')


def _linha_de_item(ctx: "Contexto", r: dict, com_resumo: bool = False) -> str:
    """Uma linha de item público na galeria e na busca. O link aponta para a página do item no catálogo pela
    rota pública `/api/publico/itens/<id>` (a única leitura anônima de item que existe hoje); o cartão de
    galeria do site é uma VITRINE, não a tela de conteúdo autenticada."""
    resumo = "<p>" + esc(r["resumo"]) + "</p>" if com_resumo and r.get("resumo") else ""
    return (f'<li><a href="/api/publico/itens/{esc(r["id"])}">{esc(r["titulo"])}</a>'
            f'<span class="site-tipo">{esc(r["tipo"])}</span>{resumo}</li>')


def cartao_galeria(ctx: Contexto, no: dict) -> str:
    """Galeria de itens do catálogo com filtro. O filtro é um `<form method="get">`: funciona sem JavaScript,
    e o servidor devolve a página já filtrada. Só entra o que `plat.site_itens_publicos` deixa passar."""
    p = _prop(no)
    campo = f"g{esc(no.get('id'))}"
    escolhido = ctx.parametros.get(campo, "")
    tipos_do_cartao = [t for t in (p.get("tipos") or []) if isinstance(t, str)]
    tipos_consulta = [escolhido] if escolhido and (not tipos_do_cartao or escolhido in tipos_do_cartao) \
        else tipos_do_cartao
    limite = p.get("limite") or limites.SITE_GALERIA_ITENS_PADRAO
    ctx.cur.execute("SELECT * FROM plat.site_itens_publicos(%s, %s::text[], NULL, %s)",
                    (ctx.tenant_id, tipos_consulta, limite))
    itens = ctx.cur.fetchall()
    filtro = ""
    if p.get("mostrar_filtro", True):
        opcoes = "".join(
            f'<option value="{esc(t)}"{" selected" if t == escolhido else ""}>{esc(t)}</option>'
            for t in (tipos_do_cartao or sorted({r["tipo"] for r in itens}))
        )
        filtro = (f'<form method="get" class="site-filtro">'
                  f'<label for="{campo}">tipo de item</label>'
                  f'<select id="{campo}" name="{campo}"><option value="">todos</option>{opcoes}</select>'
                  f'<button type="submit">filtrar</button></form>')
    linhas = "".join(_linha_de_item(ctx, r, com_resumo=True) for r in itens)
    vazio = "" if itens else "<p>nenhum item compartilhado com todos por enquanto.</p>"
    return (f'<div class="cartao cartao-galeria">{_titulo_cartao(p)}{filtro}'
            f'<ul class="site-lista">{linhas}</ul>{vazio}</div>')


def cartao_busca(ctx: Contexto, no: dict) -> str:
    """Busca de conteúdo: mesmo `tsvector` do catálogo, restrito ao que é público. Sem JavaScript: o `GET`
    volta para a mesma página com o termo, e o servidor responde com a lista."""
    p = _prop(no)
    campo = f"q{esc(no.get('id'))}"
    termo = (ctx.parametros.get(campo) or "").strip()
    resultado = ""
    if termo:
        ctx.cur.execute("SELECT * FROM plat.site_itens_publicos(%s, '{}'::text[], %s, %s)",
                        (ctx.tenant_id, termo, limites.SITE_GALERIA_ITENS_PADRAO))
        achados = ctx.cur.fetchall()
        if achados:
            linhas = "".join(_linha_de_item(ctx, r) for r in achados)
            resultado = f'<ul class="site-lista">{linhas}</ul>'
        else:
            resultado = f"<p>nada encontrado para {esc(termo)}.</p>"
    return (f'<div class="cartao cartao-busca">{_titulo_cartao(p)}'
            f'<form method="get" class="site-busca" role="search">'
            f'<label for="{campo}">{esc(p.get("rotulo_campo") or "buscar no conteúdo publicado")}</label>'
            f'<input type="search" id="{campo}" name="{campo}" value="{esc(termo)}">'
            f'<button type="submit">buscar</button></form>{resultado}</div>')


def cartao_mapa(ctx: Contexto, no: dict) -> str:
    """Mapa incorporado: o item citado tem de ser público E publicado (`/p/<inquilino>/<slug>`, item L5-14) —
    é a única vitrine anônima de documento que a plataforma tem. Sem publicação, o cartão diz isso em vez de
    mostrar um quadro quebrado."""
    p = _prop(no)
    item = _item_publico(ctx, str(p.get("item_id")))
    if item is None:
        return f'<div class="cartao cartao-mapa">{_titulo_cartao(p)}' \
               f'{_sem_acesso("o mapa deste cartão não está compartilhado com todos")}</div>'
    slug = _publicacao_do_item(ctx, str(item["id"]))
    titulo = _titulo_cartao(p) or f"<h3>{esc(item['titulo'])}</h3>"
    if slug is None:
        return f'<div class="cartao cartao-mapa">{titulo}' \
               f'{_sem_acesso("o mapa deste cartão ainda não foi publicado")}</div>'
    url = f"/p/{quote(ctx.tenant_slug)}/{quote(slug)}"
    return (f'<div class="cartao cartao-mapa">{titulo}'
            f'<iframe src="{esc(url)}" title="{esc(item["titulo"])}" height="{_altura(p)}" loading="lazy"></iframe>'
            f'<p><a href="{esc(url)}">abrir {esc(item["titulo"])} em página inteira</a></p></div>')


def cartao_aplicativo(ctx: Contexto, no: dict) -> str:
    """Cartão de app/painel: título, resumo e link para a vitrine publicada (o cartão "app" do Hub). Não
    incorpora por padrão — quem quer o quadro dentro da página usa o cartão de mapa, que é o mesmo mecanismo."""
    p = _prop(no)
    item = _item_publico(ctx, str(p.get("item_id")))
    if item is None:
        return f'<div class="cartao cartao-aplicativo">{_titulo_cartao(p)}' \
               f'{_sem_acesso("o aplicativo deste cartão não está compartilhado com todos")}</div>'
    slug = _publicacao_do_item(ctx, str(item["id"]))
    resumo = "<p>" + esc(item["resumo"]) + "</p>" if item["resumo"] else ""
    link = (f'<p><a class="site-botao" href="/p/{esc(ctx.tenant_slug)}/{esc(slug)}">abrir aplicativo</a></p>'
            if slug else _sem_acesso("aplicativo ainda não publicado"))
    titulo = _titulo_cartao(p) or "<h3>" + esc(item["titulo"]) + "</h3>"
    return (f'<div class="cartao cartao-aplicativo">{titulo}'
            f'<p class="site-tipo">{esc(item["tipo"])}</p>{resumo}{link}</div>')


def cartao_chamada(ctx: Contexto, no: dict) -> str:
    p = _prop(no)
    texto = p.get("texto")
    corpo = _paragrafos(texto) if isinstance(texto, str) and texto.strip() else ""
    return (f'<div class="cartao cartao-chamada">{_titulo_cartao(p, "h3")}{corpo}'
            f'<p><a class="site-botao" href="{esc(p.get("destino"))}">{esc(p.get("rotulo_botao"))}</a></p></div>')


def cartao_estatisticas(ctx: Contexto, no: dict) -> str:
    p = _prop(no)
    ctx.cur.execute("SELECT * FROM plat.site_estatisticas(%s)", (ctx.tenant_id,))
    linhas = ctx.cur.fetchall()
    total = sum(int(r["quantidade"]) for r in linhas)
    celulas = "".join(
        f'<div class="site-numero"><strong>{int(r["quantidade"])}</strong>'
        f'<span>{esc(FAMILIAS_ROTULO.get(r["familia"], r["familia"]))}</span></div>' for r in linhas)
    return (f'<div class="cartao cartao-estatisticas">{_titulo_cartao(p)}'
            f'<div class="site-numeros"><div class="site-numero"><strong>{total}</strong>'
            f'<span>itens compartilhados com todos</span></div>{celulas}</div></div>')


def cartao_incorporado(ctx: Contexto, no: dict) -> str:
    p = _prop(no)
    url = str(p.get("url") or "")
    titulo = p.get("titulo") or "conteúdo incorporado"
    return (f'<div class="cartao cartao-incorporado">{_titulo_cartao(p)}'
            f'<iframe src="{esc(url)}" title="{esc(titulo)}" height="{_altura(p)}" loading="lazy"'
            f' sandbox="allow-scripts allow-same-origin allow-popups" referrerpolicy="no-referrer"></iframe>'
            f'<p><a href="{esc(url)}" rel="noopener nofollow">abrir em nova página</a></p></div>')


RENDERIZADORES = {
    "texto": cartao_texto,
    "imagem": cartao_imagem,
    "galeria": cartao_galeria,
    "mapa": cartao_mapa,
    "aplicativo": cartao_aplicativo,
    "busca": cartao_busca,
    "chamada": cartao_chamada,
    "estatisticas": cartao_estatisticas,
    "incorporado": cartao_incorporado,
}
assert set(RENDERIZADORES) == CARTOES  # um renderizador por cartão do vocabulário: sem cartão mudo


def hosts_incorporados(corpo: dict) -> list[str]:
    """Origens dos cartões `incorporado`, para o `frame-src` da política de conteúdo da página (a página só
    pode emoldurar o que o próprio documento declara)."""
    saida: list[str] = []
    for n in _nos(corpo):
        if n.get("tipo") != "incorporado":
            continue
        url = str(_prop(n).get("url") or "")
        if url.startswith("https://"):
            origem = "https://" + url[len("https://"):].split("/")[0]
            if origem not in saida:
                saida.append(origem)
    return saida


# ---------------------------------------------------------------- página inteira
def _menu(ctx: Contexto, corpo: dict, atual: dict) -> str:
    itens = []
    for n in paginas(corpo):
        p = _prop(n)
        if p.get("oculta"):
            continue
        caminho = p.get("caminho") or ""
        href = f"/s/{quote(ctx.tenant_slug)}/" + (f"{quote(caminho)}" if not p.get("inicial") else "")
        marca = ' aria-current="page"' if n is atual else ""
        itens.append(f'<li><a href="{esc(href)}"{marca}>{esc(p.get("titulo") or caminho)}</a></li>')
    if not itens:
        return ""
    return f'<nav class="site-menu" aria-label="menu do site"><ul>{"".join(itens)}</ul></nav>'


def _cabecalho(ctx: Contexto, corpo: dict, atual: dict) -> str:
    nos = _nos(corpo)
    cab = _do_tipo(nos, "cabecalho")
    p = _prop(cab[0]) if cab else {}
    titulo = p.get("titulo") or ctx.tenant_nome
    subtitulo = f'<p class="site-subtitulo">{esc(p.get("subtitulo"))}</p>' if p.get("subtitulo") else ""
    logo = ""
    if p.get("mostrar_logo", True) and ctx.logo:
        logo = f'<img class="site-logo" src="/api/objetos/{esc(ctx.logo)}" alt="" width="40" height="40">'
    return (f'<header class="site-cabecalho"><div class="site-marca">{logo}'
            f'<span class="site-titulo">{esc(titulo)}</span></div>{subtitulo}{_menu(ctx, corpo, atual)}</header>')


def _rodape(ctx: Contexto, corpo: dict) -> str:
    rod = _do_tipo(_nos(corpo), "rodape")
    texto = _prop(rod[0]).get("texto") if rod else None
    corpo_rodape = _paragrafos(texto) if texto else f"<p>{esc(ctx.tenant_nome)}</p>"
    return f'<footer class="site-rodape">{corpo_rodape}<p class="site-aviso">análise / beta privado</p></footer>'


def _secoes(ctx: Contexto, corpo: dict, pagina: dict) -> str:
    nos = _nos(corpo)
    saida = []
    for secao in _do_tipo(nos, "secao", pagina.get("id")):
        p = _prop(secao)
        rotulo = p.get("rotulo")
        cabec = f"<h2>{esc(rotulo)}</h2>" if isinstance(rotulo, str) and rotulo.strip() else ""
        cartoes = []
        for filho in nos:
            if (filho.get("pai") or None) != secao.get("id"):
                continue
            desenhar = RENDERIZADORES.get(filho.get("tipo"))
            if desenhar is not None:
                cartoes.append(desenhar(ctx, filho))
        fundo = "escuro" if p.get("fundo") == "escuro" else "claro"
        rotulo_aria = esc(rotulo) if rotulo else "seção"
        saida.append(f'<section class="site-secao site-fundo-{fundo}" aria-label="{rotulo_aria}">'
                     f'{cabec}<div class="site-cartoes">{"".join(cartoes)}</div></section>')
    return "".join(saida)


def renderizar(ctx: Contexto, corpo: dict, pagina: dict) -> str:
    p = _prop(pagina)
    titulo = p.get("titulo") or ctx.tenant_nome
    robos = "index, follow" if ctx.indexavel else "noindex, nofollow"
    cor = ctx.cor if isinstance(ctx.cor, str) and ctx.cor.startswith("#") and len(ctx.cor) == 7 else "#1f4b99"
    return (
        "<!doctype html>\n"
        '<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="robots" content="{robos}">\n'
        f"<title>{esc(titulo)} · {esc(ctx.tenant_nome)}</title>\n"
        f'<link rel="stylesheet" href="{CSS}">\n'
        f'<style>:root {{ --site-cor: {esc(cor)}; --site-cor-texto: {esc(cor_do_texto(cor))}; }}</style>\n'
        "</head>\n"
        '<body class="site">\n'
        '<a class="site-pular" href="#conteudo">pular para o conteúdo</a>\n'
        f"{_cabecalho(ctx, corpo, pagina)}\n"
        f'<main id="conteudo" class="site-conteudo"><h1>{esc(titulo)}</h1>{_secoes(ctx, corpo, pagina)}</main>\n'
        f"{_rodape(ctx, corpo)}\n"
        "</body>\n</html>\n"
    )


def url_da_pagina(tenant_slug: str, caminho: str, parametros: dict | None = None) -> str:
    base = f"/s/{quote(tenant_slug)}/{quote(caminho or '')}"
    return f"{base}?{urlencode(parametros)}" if parametros else base
