"""e2e playwright da tela /amc/presets (item L3-01-h-presets) contra a URL interna real.
Prova o portão do item PELA TELA: (1) a listagem traz SEMPRE os integrados ("pesos iguais" e os
exemplos logísticos) marcados como somente leitura; (2) "novo preset" cria pela tela com conteúdo
JSON; (3) "aplicar" recalcula NA HORA, sem criar job — a tela nunca chama /api/jobs e o diálogo
mostra o resultado; (4) "exportar" abre o documento JSON e (5) "importar" recria o preset exportado.
0 erro de console; capturas em tests/e2e/capturas/L3-01-h-presets_*.png."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L3-01-h-presets"
ROTAS_PRESETS = ("/api/amc/presets", "/api/amc/presets/importar", "/api/amc/presets/{id}/aplicar")

CONTEUDO = {"fatores": ["fator_a", "fator_b"], "pesos": {"fator_a": 3.0, "fator_b": 1.0}}
MATRIZ = {"ids_fatores": ["fator_a", "fator_b"],
          "fatores": [[80.0, 40.0], [55.0, 60.0], [None, 90.0]]}


class TelaPresets(Tela):
    def capturar(self, nome):
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        caminho = CAPTURAS / f"{ITEM}_{nome}.png"
        self.page.screenshot(path=str(caminho), full_page=True)
        return caminho


@pytest.fixture(scope="session")
def api_presets(api_auth):
    faltam = [r for r in ROTAS_PRESETS if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item L3-01-h-presets)")
    return api_auth


def test_presets_lista_integrados_criar_aplicar_exportar_importar(
    page, base_url, credenciais_demo, api_presets, medida
):
    slug, login, senha = credenciais_demo
    s = sufixo()
    tela = TelaPresets(page, base_url)
    criados = []
    try:
        tela.entrar(slug, login, senha, proximo="/amc/presets")
        tela.medidas["pagina_presets_ms"] = tela.ir("/amc/presets")

        # 1) integrados SEMPRE na lista, com o marcador de integrado
        page.wait_for_selector("tr[data-integrado='true']", timeout=15000)
        nomes = page.locator("#lista-corpo tr td:first-child").all_inner_texts()
        assert "pesos iguais" in nomes and "logística: galpão" in nomes
        integrado_pesos = page.locator("tr[data-id='pesos_iguais']")
        assert "integrado" in integrado_pesos.inner_text()
        # integrado não tem botão de apagar (somente leitura; a cópia para editar existe)
        assert integrado_pesos.get_by_role("button", name="apagar").count() == 0
        tela.capturar("lista_integrados")

        # 2) novo preset pela tela (conteúdo JSON no campo de área do plat-formulario)
        page.click("#preset-novo")
        dialogo = page.locator("#dialogo dialog")
        page.fill('#dialogo input[name="nome"]', f"zt-e2e-preset-{s}")
        page.fill('#dialogo input[name="descricao"]', "criado pelo e2e do item L3-01-h")
        page.fill('#dialogo textarea[name="conteudo"]', json.dumps(CONTEUDO))
        dialogo.get_by_role("button", name="criar preset").click()
        nome_novo = f"zt-e2e-preset-{s}"
        page.wait_for_selector(f"tr[data-escopo='usuario'] td:text-is('{nome_novo}')", timeout=15000)
        linha = page.locator("#lista-corpo tr", has=page.locator(f"td:text-is('{nome_novo}')"))
        pid = linha.get_attribute("data-id")
        criados.append(pid)
        tela.capturar("criado")

        # 3) APLICAR pela tela recalcula sem job: o diálogo mostra a contagem de unidades
        linha.get_by_role("button", name="aplicar").click()
        page.fill('#dialogo textarea[name="matriz"]', json.dumps(MATRIZ))
        dialogo.get_by_role("button", name="aplicar agora").click()
        page.wait_for_selector("dialog:has-text('resultado do preset')", timeout=15000)
        resumo = page.locator("#dialogo dialog").inner_text()
        assert "3 unidades recalculadas" in resumo and "SEM criar job" in resumo
        tela.capturar("aplicado_sem_job")
        page.locator("#dialogo dialog button:text-is('fechar')").click()
        # a tela não cria job nenhum: a fila segue como estava (a rota nem toca em plat.job)
        jobs = tela.api("GET", "/api/jobs?limite=200").json()
        assert not [j for j in jobs["itens"] if "preset" in j["tipo"]]

        # 4) exportar pela tela abre o documento JSON no diálogo
        linha.get_by_role("button", name="exportar").click()
        page.wait_for_selector("#dialogo textarea[readonly]", timeout=15000)
        documento = json.loads(page.locator("#dialogo textarea[readonly]").input_value())
        assert documento["formato"] == "plat/amc_preset" and documento["conteudo"]["pesos"] == CONTEUDO["pesos"]
        tela.capturar("exportado")
        page.locator("#dialogo").evaluate("d => d.querySelector('.fechar-x').click()")

        # 5) importar pela tela recria o preset exportado (com outro nome)
        documento["nome"] = f"zt-e2e-importado-{s}"
        page.click("#preset-importar")
        page.fill('#dialogo textarea[name="documento"]', json.dumps(documento))
        page.locator("#dialogo dialog").get_by_role("button", name="importar").click()
        nome_importado = documento["nome"]
        page.wait_for_selector(f"#lista-corpo td:text-is('{nome_importado}')", timeout=15000)
        linha_imp = page.locator("#lista-corpo tr", has=page.locator(f"td:text-is('{nome_importado}')"))
        criados.append(linha_imp.get_attribute("data-id"))
        tela.capturar("importado")
    finally:
        for pid in criados:
            if pid:
                tela.api("DELETE", f"/api/amc/presets/{pid}")
    tela.verificar()
    gravar = medida(ITEM)
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms",
               "goto até body[data-pronto=1] no chromium do playwright (tests/e2e/test_amc_presets.py)")
