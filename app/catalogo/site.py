"""Construtor de SITE do inquilino (item L5-20-sites-paginas-publicas; ADR 20260908T1140-sites-paginas-publicas;
`laco/decomposicao/L5_CONCEITO.md` D10 e D24).

Um site é um item de tipo `site` cujo documento tem o MESMO envelope de app/painel do L5-05
(`corpo.nos`, lista plana, aninhamento por `pai`), montado no mesmo editor de arrasto do L5-08. O que este
módulo acrescenta é a parte que só o servidor pode fazer:

1. **Regras de montagem** que o JSON Schema do tipo não expressa: `pagina` só na raiz, cartão só dentro de
   `secao`, `secao` só dentro de `pagina`, caminho de página único, uma página inicial. Erro = 422, o
   documento não é gravado.
2. **Renderização no servidor** (D24): a página sai HTML completo, com o texto dentro do HTML, sem depender
   de JavaScript — `curl` sem navegador tem de ler o conteúdo. Não há motor de template: a casa já monta HTML
   com `html.escape` + f-string em `app/catalogo/publicacao.py::exportacao_estatica`, e Jinja2 seria
   dependência nova para repetir o que a biblioteca padrão já faz aqui (escada do Ponytail, degrau 3). Todo
   texto que vem do documento passa por `html.escape`; nenhum HTML do usuário é interpretado.
3. **Portão do que é público**: galeria, busca, estatística e os cartões que citam um item pelo uuid leem
   SÓ pelas funções `plat.site_*` da migração, que filtram `acesso = 'publico'` + `plat.tenant_permite_publico`
   (a mesma dupla de `plat.tenant_publico_itens` — a definição de "compartilhado com todos" nesta
   plataforma). O renderizador nunca consulta `plat.item` direto: item privado não sai nem por id, nem por
   busca, nem por contagem.
4. **noindex por padrão** (regra da casa): `X-Robots-Tag`/`<meta robots>` saem `noindex, nofollow` a menos que
   a publicação tenha `indexavel = true`, ligado explicitamente pelo dono do site com o aviso na tela.

O que fica de fora, declarado: markdown (o cartão de texto quebra parágrafo em linha em branco e escapa o
resto — negrito/link viriam com `markdown-it` + DOMPurify no cartão de texto rico, item de outra rodada);
página de dado aberto com DCAT/JSON-LD (L5-21, item próprio); tema além de cor/nome/logotipo do inquilino.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request

from app import limites
from app.auth.sessao import Auth, iso
from app.catalogo import tipos
from app.catalogo.comum import exigir_edicao, registrar_evento
from app.erros import ErroAPI
from app.settings import settings

FAMILIA = "site"
CAMINHO_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,58}[a-z0-9])?$")
URL_INTERNA_RE = re.compile(r"^/[A-Za-z0-9._~!$&()*+,;=:@%/?#-]*$")
URL_EXTERNA_RE = re.compile(r"^https://[a-z0-9.-]+(?::\d{1,5})?(/[^\s\"']*)?$", re.I)

# tipos de nó do documento de site: estrutura + os nove cartões da hipótese do item
ESTRUTURA = {"pagina", "cabecalho", "menu", "rodape", "secao"}
CARTOES = {
    "texto", "imagem", "galeria", "mapa", "aplicativo", "busca", "chamada", "estatisticas", "incorporado",
}
TIPOS_NO = ESTRUTURA | CARTOES
FAMILIAS_ROTULO = {
    "camada": "camadas", "raster": "imagens", "mapa": "mapas", "app": "aplicativos", "painel": "painéis",
    "formulario": "formulários", "fluxo": "fluxos", "rede": "redes", "arquivo": "arquivos",
    "ferramenta": "ferramentas", "documento": "documentos", "site": "sites",
}


# ---------------------------------------------------------------- validação do documento
def _prop(no: dict) -> dict:
    p = no.get("propriedades")
    return p if isinstance(p, dict) else {}


def _erro(erros: list[dict], campo: str, mensagem: str, regra: str) -> None:
    erros.append({"campo": campo, "erro": mensagem, "regra": regra})


def validar_documento(tipo: str, dados: Any) -> None:
    """422 `site_invalido` quando a montagem viola uma regra que o JSON Schema do tipo não alcança. Chamada
    junto de `documento.validar_grafo` nas duas rotas que gravam `dados` (POST e PATCH de item)."""
    if tipos.familia_de(tipo) != FAMILIA:
        return
    corpo = (dados or {}).get("corpo") if isinstance(dados, dict) else None
    if not isinstance(corpo, dict):
        return
    nos = corpo.get("nos")
    if not isinstance(nos, list):
        return
    erros: list[dict] = []
    if len(nos) > limites.SITE_NOS_MAX:
        _erro(erros, "corpo.nos", f"o site tem no máximo {limites.SITE_NOS_MAX} nós", "nos_demais")
    por_id = {n.get("id"): n for n in nos if isinstance(n, dict) and isinstance(n.get("id"), str)}
    caminhos: dict[str, int] = {}
    iniciais = 0
    paginas = 0
    for i, n in enumerate(nos):
        if not isinstance(n, dict):
            continue
        t = n.get("tipo")
        pai = n.get("pai")
        campo = f"corpo.nos.{i}"
        if t not in TIPOS_NO:
            _erro(erros, f"{campo}.tipo", f"tipo de nó fora do vocabulário do site: {t}", "tipo_de_no")
            continue
        pai_no = por_id.get(pai) if pai else None
        if pai and pai_no is None:
            _erro(erros, f"{campo}.pai", "pai inexistente no documento", "pai_inexistente")
            continue
        tipo_pai = pai_no.get("tipo") if pai_no else None
        if t == "pagina":
            paginas += 1
            if pai:
                _erro(erros, f"{campo}.pai", "página só existe na raiz do documento", "pagina_na_raiz")
            caminho = _prop(n).get("caminho")
            if not isinstance(caminho, str) or not CAMINHO_RE.match(caminho):
                _erro(erros, f"{campo}.propriedades.caminho",
                      "caminho da página: minúsculas, dígitos e hífen", "caminho_invalido")
            else:
                caminhos[caminho] = caminhos.get(caminho, 0) + 1
            if _prop(n).get("inicial"):
                iniciais += 1
        elif t in ("cabecalho", "rodape", "menu"):
            if pai is not None:
                _erro(erros, f"{campo}.pai", f"{t} pertence ao site inteiro, não a uma página", "no_na_raiz")
        elif t == "secao":
            if tipo_pai != "pagina":
                _erro(erros, f"{campo}.pai", "seção só entra dentro de uma página", "secao_na_pagina")
        else:  # cartão
            if tipo_pai != "secao":
                _erro(erros, f"{campo}.pai", "cartão só entra dentro de uma seção", "cartao_na_secao")
            erros.extend(_erros_do_cartao(campo, t, _prop(n)))
    if paginas > limites.SITE_PAGINAS_MAX:
        _erro(erros, "corpo.nos", f"o site tem no máximo {limites.SITE_PAGINAS_MAX} páginas", "paginas_demais")
    for caminho, quantas in caminhos.items():
        if quantas > 1:
            _erro(erros, "corpo.nos", f"duas páginas com o mesmo caminho: {caminho}", "caminho_repetido")
    if iniciais > 1:
        _erro(erros, "corpo.nos", "só uma página pode ser a inicial", "inicial_repetida")
    if erros:
        raise ErroAPI(422, "site_invalido", "documento de site fora das regras de montagem", erros)


def _erros_do_cartao(campo: str, tipo_cartao: str, p: dict) -> list[dict]:
    erros: list[dict] = []
    c = f"{campo}.propriedades"
    if tipo_cartao == "texto":
        texto = p.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            _erro(erros, f"{c}.texto", "o cartão de texto precisa de texto", "obrigatorio")
        elif len(texto) > limites.SITE_TEXTO_MAX:
            _erro(erros, f"{c}.texto", f"máximo de {limites.SITE_TEXTO_MAX} caracteres", "maxLength")
    elif tipo_cartao == "imagem":
        url = p.get("url")
        if not isinstance(url, str) or not URL_INTERNA_RE.match(url):
            # imagem de fora seria requisição a terceiro dentro da página do inquilino (mesma regra do L5-08)
            _erro(erros, f"{c}.url", "a imagem tem de vir do próprio servidor (caminho começando por /)",
                  "url_interna")
        if not isinstance(p.get("alternativo"), str) or not p["alternativo"].strip():
            _erro(erros, f"{c}.alternativo", "texto alternativo é obrigatório em imagem", "obrigatorio")
    elif tipo_cartao in ("mapa", "aplicativo"):
        if not isinstance(p.get("item_id"), str):
            _erro(erros, f"{c}.item_id", "o cartão cita um item do catálogo pelo uuid", "obrigatorio")
    elif tipo_cartao == "chamada":
        destino = p.get("destino")
        if not isinstance(destino, str) or not (URL_INTERNA_RE.match(destino) or URL_EXTERNA_RE.match(destino)):
            _erro(erros, f"{c}.destino", "destino do botão: caminho interno ou endereço https", "destino_invalido")
        if not isinstance(p.get("rotulo_botao"), str) or not p["rotulo_botao"].strip():
            _erro(erros, f"{c}.rotulo_botao", "o botão precisa de rótulo", "obrigatorio")
    elif tipo_cartao == "incorporado":
        url = p.get("url")
        if not isinstance(url, str) or not URL_EXTERNA_RE.match(url):
            _erro(erros, f"{c}.url", "o conteúdo incorporado tem de vir por https", "url_https")
    elif tipo_cartao == "galeria":
        limite = p.get("limite")
        if limite is not None and (not isinstance(limite, int) or isinstance(limite, bool)
                                   or not 1 <= limite <= limites.SITE_GALERIA_ITENS_MAX):
            _erro(erros, f"{c}.limite", f"entre 1 e {limites.SITE_GALERIA_ITENS_MAX}", "faixa")
    return erros


# ---------------------------------------------------------------- publicação (uma por inquilino)
def _site_json(r: dict) -> dict:
    return {
        "item_id": str(r["item_id"]),
        "tenant_slug": r["tenant_slug"],
        "url": f"{settings.PLAT_URL_PUBLICA}/s/{r['tenant_slug']}/",
        "indexavel": bool(r["indexavel"]),
        "versao_publicada": r["versao_publicada"],
        "publicado_em": iso(r["publicado_em"]),
        "atualizado_em": iso(r["atualizado_em"]),
    }


def estado(cur, item_id: str) -> dict | None:
    cur.execute(
        "SELECT s.*, t.slug AS tenant_slug, i.versao_publicada FROM plat.site_publicado s "
        "JOIN plat.tenant t ON t.id = s.tenant_id JOIN plat.item i ON i.id = s.item_id "
        "WHERE s.item_id = %s::uuid",
        (item_id,),
    )
    r = cur.fetchone()
    return _site_json(r) if r is not None else None


def publicar(cur, request: Request, auth: Auth, item_id: str, indexavel: bool, versao: int | None) -> dict:
    r = exigir_edicao(cur, item_id)
    if tipos.familia_de(r["tipo"]) != FAMILIA:
        raise ErroAPI(422, "tipo_nao_publicavel", "só um item de tipo site publica em /s/")
    alvo = versao if versao is not None else r["versao_atual"]
    cur.execute("SELECT 1 FROM plat.item_versao WHERE item_id = %s::uuid AND versao = %s", (item_id, alvo))
    if cur.fetchone() is None:
        raise ErroAPI(404, "versao_inexistente", "versão inexistente")
    cur.execute("SELECT item_id FROM plat.site_publicado WHERE tenant_id = %s", (auth.tenant_id,))
    outro = cur.fetchone()
    if outro is not None and str(outro["item_id"]) != item_id:
        raise ErroAPI(409, "site_em_uso", "este inquilino já tem um site publicado; retire-o do ar antes")
    cur.execute("UPDATE plat.item SET versao_publicada = %s WHERE id = %s::uuid", (alvo, item_id))
    cur.execute(
        """
        INSERT INTO plat.site_publicado(tenant_id, item_id, indexavel, publicado_por, publicado_em, atualizado_em)
        VALUES (%s, %s::uuid, %s, %s, now(), now())
        ON CONFLICT (tenant_id) DO UPDATE SET item_id = EXCLUDED.item_id, indexavel = EXCLUDED.indexavel,
            publicado_por = EXCLUDED.publicado_por, atualizado_em = now()
        """,
        (auth.tenant_id, item_id, indexavel, auth.usuario_id),
    )
    registrar_evento(cur, request, "site/publicar", "item", item_id,
                     {"versao": alvo, "indexavel": indexavel})
    return estado(cur, item_id)


def despublicar(cur, request: Request, item_id: str) -> None:
    exigir_edicao(cur, item_id)
    cur.execute("SELECT tenant_id FROM plat.site_publicado WHERE item_id = %s::uuid", (item_id,))
    if cur.fetchone() is None:
        raise ErroAPI(404, "site_inexistente", "este site não está publicado")
    cur.execute("DELETE FROM plat.site_publicado WHERE item_id = %s::uuid", (item_id,))
    registrar_evento(cur, request, "site/despublicar", "item", item_id, {})


# ---------------------------------------------------------------- leitura pública
def resolver(cur, tenant_slug: str) -> dict:
    cur.execute("SELECT * FROM plat.site_resolver(%s)", (tenant_slug,))
    r = cur.fetchone()
    if r is None or r["motivo"] != "ok":
        raise ErroAPI(404, "site_inexistente", "site inexistente")
    return r


def corpo_publicado(cur, item_id: str, versao: int) -> dict:
    cur.execute("SELECT plat.site_corpo(%s::uuid, %s) AS corpo", (item_id, versao))
    r = cur.fetchone()
    retrato = (r or {}).get("corpo")
    if not isinstance(retrato, dict):
        raise ErroAPI(404, "site_inexistente", "versão publicada inexistente")
    dados = retrato.get("dados")
    # `item_versao.corpo` é o RETRATO do item inteiro; o grafo do site é `dados.corpo` (nós e ligações), que
    # é o que o renderizador espera — devolver `dados` daria uma página sem nenhuma seção, em silêncio.
    corpo = dados.get("corpo") if isinstance(dados, dict) else None
    return corpo if isinstance(corpo, dict) else {}
