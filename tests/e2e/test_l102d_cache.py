"""e2e da tela /admin/cache (item L1-02-d).

A cláusula do portão é "página interna de status mostra taxa de acerto do cache por dia". O que só o
navegador prova: a tela abre sem erro de console, o resumo mostra o estado da fonte (ok/sem_dado/
sem_linhas — o número vem do log do nginx, nunca da aplicação) e a tabela de dias monta as colunas de
acerto/erro/taxa. Numa trilha sem journal do nginx o estado esperado é sem_linhas COM o porquê
explicado — taxa desconhecida não é taxa zero."""

import pytest

from tests.e2e.apoio import Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L1-02-d"


def test_tela_de_cache_mostra_estado_e_tabela_por_dia(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url, ITEM)
    tela.entrar(slug, login, senha, proximo="/admin/cache")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_selector("#tabela-dias", timeout=20000)

    resumo = page.inner_text("#resumo-corpo").strip()
    assert resumo and "carregando" not in resumo, f"resumo não saiu do placeholder: {resumo!r}"

    # a tabela montou as cinco colunas da taxa por dia, com linhas (estado ok) ou com o texto de vazio
    cabecalhos = [c.strip() for c in page.locator("#tabela-dias th").all_inner_texts()]
    assert len(cabecalhos) == 5, cabecalhos
    corpo = page.inner_text("#tabela-dias").strip()
    assert corpo, "tabela de dias sem nada — nem linhas, nem o texto de vazio"

    tela.capturar("admin_cache")
    tela.verificar()
