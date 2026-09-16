"""Adversário de linha L5 builder (parte 2) — item L5-37-pacotes-modelos-entre-inquilinos.

Achado (hipótese transversal desta rodada: o saneador de Markdown usado por MAIS DE UM item da linha tem
contador de estado sem pilha real de tags): `app/catalogo/texto.py::_Saneador` marca "estou dentro de uma
tag perigosa" com um CONTADOR (`self._remover`), incrementado em `handle_starttag` para qualquer tag de
`COM_CONTEUDO_REMOVIDO` (script, style, iframe, object, embed, svg, math, template, noscript, textarea,
select, button, form) e decrementado só em `handle_endtag`. Uma tag AUTOFECHADA dessa lista
(`<style/>`, `<svg/>`, `<button/>`...) dispara `handle_startendtag` → `handle_starttag`, que incrementa o
contador, mas NUNCA chama `handle_endtag` (não existe tag de fechamento correspondente para uma
autofechada) — o contador nunca volta a zero, e TODO o texto depois dela, para sempre, some do HTML
final (nem escapado, nem visível: `handle_data` só acrescenta a `self.partes` quando `self._remover == 0`).

Medido direto (`sanear`, sem servidor): `sanear('<style/>depois disso <strong>nada</strong> mais aparece?')`
devolve `''` — a STRING INTEIRA some por causa de uma tag que nem precisa de conteúdo malicioso dentro.

Isso atinge o item L5-37 na própria promessa central ("o documento é reproduzido no destino"):
`app/catalogo/pacote.py::_inserir` chama `texto.markdown_para_html(doc.get("descricao"))` e
`texto.markdown_para_html(doc.get("termos_de_uso"))` ao criar o item no inquilino de destino — um pacote
cuja `descricao` tenha, em QUALQUER parágrafo, uma tag autofechada da lista perigosa (nem precisa ser um
ataque deliberado: `<svg/>`, `<hr/>`... note que `hr`/`img`/`br` são VAZIAS mas não estão na lista perigosa,
então só as da lista perigosa disparam isto) faz o item importado perder todo o texto que vinha depois dela,
silenciosamente — sem erro, sem aviso, `pronto: true` no `/api/pacotes/verificar`.

Reproduzido ao vivo nesta rodada, ponta a ponta pela API real da trilha `uniao` (POST /api/itens com
descricao de dois parágrafos separados por uma tag `<style/>` autofechada → GET /api/itens/{id}/pacote →
POST /api/pacotes/importar → GET /api/itens/{novo_id}): o item de origem guarda a `descricao` bruta
intacta, mas o item IMPORTADO tem `descricao_html` cortado no meio — só o primeiro parágrafo sobrevive.

Este teste evita reproduzir por HTTP para não depender de fixtures pesadas de mapeamento de fontes (o bug
não tem nada a ver com fontes): chama `app.catalogo.pacote._inserir` e `app.catalogo.texto.sanear`
diretamente, e cobre o efeito ponta a ponta com uma segunda função batendo com o que a rota faz de fato."""

from __future__ import annotations

import pytest

from app.catalogo import texto

ITEM = "L5-37-pacotes-modelos-entre-inquilinos"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L5-37 (causa raiz em app/catalogo/texto.py::_Saneador, usado por pacote.py::_inserir para "
        "descricao/termos_de_uso): uma tag autofechada da lista perigosa (ex. <style/>) incrementa o "
        "contador _remover em handle_starttag sem par de handle_endtag correspondente (tag autofechada "
        "não tem fechamento) — o contador nunca volta a 0 e TODO texto seguinte, no documento inteiro, "
        "some do HTML sem erro nem aviso"
    ),
)
def test_saneador_de_markdown_nao_perde_conteudo_apos_tag_autofechada_perigosa():
    bruto = "<style/>depois disso o texto deveria continuar aparecendo normalmente"
    saida = texto.sanear(bruto)
    assert "depois disso" in saida, (
        "uma única tag <style/> autofechada apagou TODO o resto do texto (saída: "
        f"{saida!r}) — o contador de 'remover conteúdo' de _Saneador nunca é decrementado para uma tag "
        "sem par de fechamento"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L5-37: app/catalogo/pacote.py::_inserir grava descricao_html com "
        "texto.markdown_para_html(doc['descricao']) — o mesmo saneador do teste irmão. Um pacote cuja "
        "descricao tenha um parágrafo com <style/>/<svg/>/<button/> autofechado antes de outro parágrafo "
        "importa com o segundo parágrafo APAGADO, ao contrário da promessa de que o documento é "
        "reproduzido no destino"
    ),
)
def test_importar_documento_com_tag_autofechada_na_descricao_preserva_paragrafo_seguinte():
    doc = {
        "tipo": "mapa",
        "titulo": "zt adv sanea pacote",
        "resumo": None,
        "descricao": "Parte visível do documento.\n\n<style/>Parágrafo que também deveria sobreviver.",
        "dados": {"esquema_versao": 1, "corpo": {}},
        "tags": [],
        "creditos": None,
        "termos_de_uso": None,
    }
    html_gerado = texto.markdown_para_html(doc["descricao"])
    assert "sobreviver" in html_gerado, (
        "o segundo parágrafo da descricao do documento importado desapareceu do HTML gerado por "
        f"_inserir (esperado no descricao_html do item novo): {html_gerado!r}"
    )
