"""e2e do item L5-13-edicao-concorrente (dois navegadores = duas páginas do mesmo contexto, cada uma com a própria
aba do construtor): (1) editam nós DIFERENTES e ambos salvam sem conflito — o segundo recebe a mesclagem do
servidor e o documento final tem as duas edições; (2) editam o MESMO nó — 409 com a diferença mostrada e o nó em
conflito marcado; (3) a presença de quem entra aparece na outra aba em <= 2 s (medido); (4) bloqueio leve: quem
seleciona um nó que outra aba já tem selecionado recebe aviso, sem travar; (5) refutação: rede lenta (o PATCH de
uma aba fica retido pelo playwright >= 3 s e é liberado depois de a outra gravar) nos dois sentidos — nenhuma
alteração perdida sem aviso. Presença bate a cada `?presenca_ms=` (só o teste encurta; padrão 5 s)."""

from __future__ import annotations

import time

import pytest

from tests.e2e.apoio import Tela, sufixo
from tests.e2e.test_desfazer_refazer_rascunho import _adicionar_por_teclado, _criar_item, _item

ITEM = "L5-13-edicao-concorrente"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _abrir_duas(context, page, base_url, credenciais, iid, presenca_ms=1000):
    slug, login, senha = credenciais
    tela_a = Tela(page, base_url)
    tela_a.entrar(slug, login, senha)
    pagina_b = context.new_page()
    tela_b = Tela(pagina_b, base_url)
    caminho = f"/construtor?item={iid}&presenca_ms={presenca_ms}"
    tela_a.ir(caminho)
    page.wait_for_selector("#tela", timeout=10000)
    return tela_a, tela_b, pagina_b, caminho


def _gravado(page, prefixo="gravado", timeout=15000):
    page.wait_for_function(
        "(p) => document.getElementById('estado-salvo').textContent.startsWith(p)", arg=prefixo, timeout=timeout
    )
    return page.text_content("#estado-salvo")


def _editar_texto(page, no_id, texto):
    page.click(f'.no-editor[data-no="{no_id}"]')
    page.fill('[data-prop="texto"]', texto)
    page.keyboard.press("Tab")
    page.wait_for_function(
        "() => document.getElementById('estado-salvo').textContent.includes('não gravadas')", timeout=5000
    )


def test_nos_diferentes_ambos_salvam_sem_conflito_e_presenca_em_2s(
    context, page, base_url, credenciais_demo, admin_api, medida
):
    iid = _criar_item(admin_api, f"zt-conc-disjuntos-{sufixo()}")
    tela_a, tela_b, pagina_b, caminho = _abrir_duas(context, page, base_url, credenciais_demo, iid)
    # presença: B entra; A vê B em <= 2 s
    t0 = time.perf_counter()
    tela_b.ir(caminho)
    pagina_b.wait_for_selector("#tela", timeout=10000)
    page.wait_for_selector("#presenca li[data-sessao]", timeout=5000)
    presenca_s = time.perf_counter() - t0
    assert page.get_attribute("#presenca", "data-outros") == "1"
    pagina_b.wait_for_selector("#presenca li[data-sessao]", timeout=5000)
    # A adiciona um grupo e salva (v2); B, com a base antiga, adiciona um texto e salva: mesclado, sem 409
    no_a = _adicionar_por_teclado(page, "grupo")
    page.click("#salvar")
    assert _gravado(page).startswith("gravado (versão 2)")
    no_b = _adicionar_por_teclado(pagina_b, "texto")
    pagina_b.click("#salvar")
    estado_b = _gravado(pagina_b)
    assert "mesclado" in estado_b, estado_b
    assert pagina_b.locator("#conflito-versao").count() == 0
    # B passou a ver o grupo de A no editor dela (documento absorvido), e o servidor tem os dois nós
    pagina_b.wait_for_selector(f'.no-editor[data-no="{no_a}"]', timeout=5000)
    assert pagina_b.locator(f'.no-editor[data-no="{no_b}"]').count() == 1
    final = _item(admin_api, iid)
    ids = [n["id"] for n in final["dados"]["corpo"]["nos"]]
    assert no_a in ids and no_b in ids and final["versao_atual"] == 3
    # B continua editando normalmente depois da mesclagem (base atualizada): sem 409 na próxima gravação
    _adicionar_por_teclado(pagina_b, "texto")
    pagina_b.click("#salvar")
    assert _gravado(pagina_b).startswith("gravado (versão 4)")
    tela_a.verificar()
    tela_b.verificar()
    m = medida(ITEM)
    m("presenca_aparece_s", round(presenca_s, 3), "s",
      "B abre o construtor -> li[data-sessao] na aba A (SSE + batimento)")
    m("nos_diferentes_sem_conflito", True, "bool", "grupo por A (v2) + texto por B com base v1 -> 200 mesclado (v3)")


def test_mesmo_no_e_409_com_diferenca_e_no_em_conflito_marcado(context, page, base_url, credenciais_demo, admin_api):
    iid = _criar_item(admin_api, f"zt-conc-mesmo-no-{sufixo()}")
    tela_a, tela_b, pagina_b, caminho = _abrir_duas(context, page, base_url, credenciais_demo, iid)
    no = _adicionar_por_teclado(page, "texto")
    page.click("#salvar")
    _gravado(page)
    tela_b.ir(caminho)
    pagina_b.wait_for_selector(f'.no-editor[data-no="{no}"]', timeout=10000)
    # os dois mudam o MESMO nó; A grava primeiro
    _editar_texto(page, no, "texto de A")
    _editar_texto(pagina_b, no, "texto de B")
    page.click("#salvar")
    _gravado(page)
    tela_b.esperar_status(409)
    pagina_b.click("#salvar")
    pagina_b.wait_for_selector("#conflito-versao", timeout=10000)
    painel = pagina_b.text_content("#conflito-versao")
    assert "mesmo nó" in painel and "nó(s) em conflito: 1" in painel
    assert pagina_b.get_attribute("#conflito-versao", "data-conflitos") == no
    pagina_b.wait_for_selector(f'#conflito-versao .diferenca-arvore li[data-no="{no}"].em-conflito', timeout=5000)
    # nada perdido nem escolhido: servidor tem A, B ainda tem o texto dela na tela
    assert _item(admin_api, iid)["dados"]["corpo"]["nos"][0]["propriedades"]["texto"] == "texto de A"
    pagina_b.click(f'.no-editor[data-no="{no}"]')
    assert pagina_b.input_value('[data-prop="texto"]') == "texto de B"
    # B decide: gravar a dela no nó em conflito (escolha explícita) -> vira v4 com "texto de B"
    pagina_b.click("#conflito-versao button:has-text('Gravar a minha nos nós em conflito')")
    _gravado(pagina_b)
    assert _item(admin_api, iid)["dados"]["corpo"]["nos"][0]["propriedades"]["texto"] == "texto de B"
    tela_a.verificar()
    tela_b.verificar()


def test_bloqueio_leve_avisa_quem_entra_no_mesmo_no_sem_travar(context, page, base_url, credenciais_demo, admin_api):
    iid = _criar_item(admin_api, f"zt-conc-bloqueio-{sufixo()}")
    tela_a, tela_b, pagina_b, caminho = _abrir_duas(context, page, base_url, credenciais_demo, iid)
    no = _adicionar_por_teclado(page, "texto")
    page.click("#salvar")
    _gravado(page)
    tela_b.ir(caminho)
    pagina_b.wait_for_selector(f'.no-editor[data-no="{no}"]', timeout=10000)
    page.click(f'.no-editor[data-no="{no}"]')  # A seleciona o nó (bate na hora)
    pagina_b.wait_for_selector(f'.no-editor[data-no="{no}"][data-ocupado]', timeout=5000)
    assert pagina_b.is_hidden("#aviso-no-ocupado")
    pagina_b.click(f'.no-editor[data-no="{no}"]')  # B entra no mesmo nó: aviso, não trava
    pagina_b.wait_for_selector("#aviso-no-ocupado:not([hidden])", timeout=5000)
    assert "também está neste nó" in pagina_b.text_content("#aviso-no-ocupado")
    _editar_texto(pagina_b, no, "B editou mesmo assim")  # não trava
    pagina_b.click("#salvar")
    _gravado(pagina_b)
    tela_a.verificar()
    tela_b.verificar()


def _reter(pagina, retidos):
    """O PATCH desta aba fica RETIDO (route sem continue_) até `_liberar`: um sleep dentro do handler travaria o
    processo do teste inteiro (as duas páginas) e a ordem nunca inverteria de verdade."""
    def rota(route, request):
        if request.method == "PATCH":
            retidos.append(route)
            return
        route.continue_()
    pagina.route("**/api/itens/*", rota)


def _liberar(pagina, retidos, apos_s=3.0):
    time.sleep(apos_s)
    for r in retidos:
        r.continue_()
    retidos.clear()
    pagina.unroute("**/api/itens/*")


def test_adversario_rede_lenta_e_gravacoes_fora_de_ordem_nao_perdem_nada(
    context, page, base_url, credenciais_demo, admin_api, medida
):
    """A clica Salvar com o PATCH retido >= 3 s; B, sem atraso, edita OUTRO nó e salva primeiro. Quando o PATCH de
    A é liberado, a base dele é antiga: o servidor mescla por nó. Depois o inverso (B retida, A primeiro). Ao fim,
    as 4 edições estão no servidor e nas duas telas; nenhum 409, nenhum aviso."""
    iid = _criar_item(admin_api, f"zt-conc-lenta-{sufixo()}")
    tela_a, tela_b, pagina_b, caminho = _abrir_duas(context, page, base_url, credenciais_demo, iid)
    tela_b.ir(caminho)
    pagina_b.wait_for_selector("#tela", timeout=10000)
    # rodada 1: A retida, B rápida grava primeiro
    retidos_a: list = []
    _reter(page, retidos_a)
    no_a1 = _adicionar_por_teclado(page, "grupo")
    page.click("#salvar")
    no_b1 = _adicionar_por_teclado(pagina_b, "texto")
    pagina_b.click("#salvar")
    assert _gravado(pagina_b).startswith("gravado (versão 2)")
    _liberar(page, retidos_a)
    estado_a = _gravado(page, timeout=20000)
    assert "mesclado" in estado_a, estado_a
    # rodada 2: B retida, A rápida (fora de ordem no outro sentido)
    retidos_b: list = []
    _reter(pagina_b, retidos_b)
    no_b2 = _adicionar_por_teclado(pagina_b, "texto")
    pagina_b.click("#salvar")
    no_a2 = _adicionar_por_teclado(page, "grupo")
    page.click("#salvar")
    assert _gravado(page).startswith("gravado (versão 4)")
    _liberar(pagina_b, retidos_b)
    estado_b = _gravado(pagina_b, timeout=20000)
    assert "mesclado" in estado_b, estado_b
    final = _item(admin_api, iid)
    ids = {n["id"] for n in final["dados"]["corpo"]["nos"]}
    assert {no_a1, no_b1, no_a2, no_b2} <= ids and final["versao_atual"] == 5
    for pg in (page, pagina_b):
        for nid in (no_a1, no_b1, no_a2, no_b2):
            pg.wait_for_selector(f'.no-editor[data-no="{nid}"]', timeout=5000)
        assert pg.locator("#conflito-versao").count() == 0
    tela_a.verificar()
    tela_b.verificar()
    medida(ITEM)("rede_lenta_alteracoes_perdidas", 0, "alteracoes",
                 "2 rodadas com PATCH retido >= 3 s (playwright route) e liberado depois da outra aba gravar; "
                 "4 nós no servidor e nas 2 telas")
